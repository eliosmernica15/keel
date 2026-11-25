# Keel Desktop — installation guide (truthful distribution state)

**Owner:** Agent H (documentation / licensing). **Date:** 2026-11-25;
**reconciled 2026-11-25** with concurrent packaging changes from Agent E.
**Scope:** documentation only. No generated registry, source manifest, license
term, release workflow or generated file was changed by this document.

> **Read this first — no public installer exists yet.** `keel/site/download.json`
> reports every channel as `available: false` / `verified: false` with no URL,
> and `site/api/download-manifest.js` returns `503 manifest_not_configured`
> until an owner configures `KEEL_DOWNLOAD_MANIFEST_URL`. No GitHub Release has
> been published. A real `keel.release publish` is **hard-gated** on an
> owner-supplied Ed25519 release-signing key (§7). Installers that have been
> built locally are **unsigned and not notarized**. This guide describes the
> intended install flow and what is currently true; it is **not** a claim that
> a signed, production-ready public release exists.

---

## 1. What the packaging configuration targets

Source of truth: `keel/desktop-app/package.json` (`build.win`, `build.mac`,
`build.linux`, `build.nsis`, `build.pkg`), `keel/src/keel/release/common.py`
(`CHANNELS`, `build_fallback_download_manifest`) and the static acceptance
checks in `keel/src/keel/release/packaging.py`.

| Platform | Primary artifact | Alternative(s) | Architecture | Current availability |
|---|---|---|---|---|
| Windows | `Keel-Setup-<version>.exe` (NSIS wizard) | none | x64 | Not hosted; `available: false` |
| macOS | `Keel-<version>-macos-arm64.pkg` (Apple Silicon) | `Keel-<version>-macos-x64.pkg` (Intel) | arm64 primary, x64 alternative | Not hosted; `available: false` |
| Linux | `Keel-<version>-linux-amd64.deb` (Debian/Ubuntu) | `Keel-<version>-linux-x86_64.rpm` (Fedora/RHEL) | x86_64 | Not hosted; `available: false` |

The product uses **native OS installers on every platform**: NSIS EXE, macOS
PKG and Linux DEB/RPM. `packaging.py` rejects archive-only or archive-primary
configuration (`linux.target` must not contain AppImage; `CHANNELS` must not
advertise `.dmg` / `.zip` / `AppImage`; macOS primary must end in `.pkg`, Linux
primary in `.deb`). Earlier in this round the manifest listed DMG/ZIP/AppImage;
that configuration is superseded. See §8 for the still-stale committed fallback
file.

**Windows on ARM is not built.** The download UX reports a native Windows ARM
build as unpublished and suggests running x64 under emulation on Windows 11
ARM (`download.js` → `isUnsupported` / `unsupportedNote`).

**macOS architecture is an explicit choice.** Browsers do not reliably expose
Intel vs Apple Silicon, so the download UX never silently picks one: it asks
the user to confirm when the architecture cannot be determined and more than
one PKG is listed. Both arm64 and x64 PKGs are configured; neither is publicly
verified yet.

**Linux package family is an explicit choice.** The site never guesses DEB vs
RPM from the user agent. The manifest lists DEB as primary and RPM as the
alternative; the page exposes both as selectable variants.

**Static acceptance checks exist but are not an install test.**
`python -m keel.release check-packaging` validates package identity
(`appId: app.keel.desktop`, `productName: Keel`, version `0.1.1`), NSIS wizard
settings and branding assets, the macOS PKG targets/icons, and Linux DEB/RPM
targets, desktop icons and runtime dependencies. This document does not assert
a pass result; run the command to see the current one. `build.py` now runs
`check_packaging_config()` before a build and `check_built_inventory()` after
it, and uses `npm ci` so the pinned `electron-builder` is honoured.

---

## 2. Install — Windows (NSIS EXE)

1. Download `Keel-Setup-<version>.exe` **only** from a link the `/download` page
   enabled after manifest verification (or from the verified release asset).
   Do not run a file whose SHA-256 does not match (§6).
2. Run the EXE. The installer is **per-user** (`perMachine: false`): no
   administrator elevation is required. A custom install-directory choice and
   Desktop / Start Menu shortcuts (`shortcutName: Keel`) are offered.
3. Finish, then launch Keel from the Start Menu or Desktop shortcut
   (`runAfterFinish: true`). Setup text is in
   `keel/desktop-app/build/nsis-keel.nsh`.
4. First run starts the bundled local bridge (`keel.exe serve`) over loopback
   with a per-session token; the packaged Electron shell loads the full local
   `desktop/ui`. No account or cloud relay is required.

**Unsigned warning:** SmartScreen / "Windows protected your PC" will warn.
This is expected until an owner provisions an Authenticode certificate (§7).
Verify the checksum rather than relying on the warning as a trust signal.

---

## 3. Install — macOS (native PKG)

1. Download the correct PKG: `Keel-<version>-macos-arm64.pkg` for Apple
   Silicon, `Keel-<version>-macos-x64.pkg` for Intel. If the page cannot confirm
   the architecture, choose it yourself — do not guess.
2. Open the PKG. `build.pkg.installLocation = "/Applications"`,
   `isRelocatable = true`, `isVersionChecked = true`, and
   `overwriteAction = "upgrade"`: the installer places Keel in
   `/Applications` and upgrades an existing copy rather than duplicating it.
   Bundle id is `app.keel.desktop`.
3. Because the package/app is **unsigned and not notarized**, macOS may refuse
   to open it or block first launch. If Gatekeeper blocks, right-click Keel →
   **Open** → confirm; do not disable Gatekeeper globally. Notarization and
   Developer ID verification (`codesign`, `spctl`, `xcrun stapler validate`)
   are **not configured**.

**Evidence boundary:** the PKG target, install location and both architectures
are *configuration* facts (`package.json`, `packaging.py`, `common.MACOS_NOTES`).
No macOS native-runner build, notarization or GUI launch was executed on this
host; historical 0.1.0 CI artifacts are not a 0.1.1 acceptance result.

---

## 4. Install — Linux (DEB / RPM)

Choose the package family yourself; the site does not guess it.

**Debian / Ubuntu (.deb):**

```bash
sudo apt install ./Keel-<version>-linux-amd64.deb
```

Declared dependencies: `libgtk-3-0`, `libnss3`, `libasound2`
(`desktop-app/package.json` → `build.deb.depends`). The package includes a
desktop entry and icons (`packaging.py` checks the icon sizes).

**Fedora / RHEL (.rpm):**

```bash
sudo dnf install ./Keel-<version>-linux-x86_64.rpm
```

Launch Keel from your desktop's application menu. No AppImage is produced or
advertised in the current configuration.

**Evidence boundary:** native packages are described as built on a Linux CI
runner and structure-inspected, but **not launched on desktop Linux** in this
workstream (`common.LINUX_NOTES`, `FINAL-RELEASE-OPERATIONS.md` §4).

---

## 5. Upgrade, uninstall and user-data preservation

### Upgrade

- **Automatic in-app upgrade is not active in the shipped build.** The
  packaged metadata `resources/app-update.yml` points at the GitHub provider
  `eliosmernica15/keel`, but `desktop-app/main.js` has update-*check* plumbing
  only; there is no wired in-app updater. `keel/src/keel/release/updater.py`
  provides `check_for_update`, `download_update`, `atomic_install` and
  `rollback` (atomic directory swap, previous version kept for rollback, no
  install touched on failed verification), but they are not connected to the
  packaged app in this round.
- **Supported upgrade today:** download the newer verified installer and run
  it over the existing installation. On macOS, `build.pkg.overwriteAction =
  "upgrade"` handles replacement; on Windows and Linux the package manager /
  NSIS wizard replaces application files. Keel user state lives outside the
  application directory, so reinstalling does not reset it.
- The release manifest carries `min_version`, `blocked_versions` and staged
  `rollout` settings consumed by `updater.py`, not by the current site or
  installer.

### Uninstall and `~/.keel`

Keel user data lives in `~/.keel` (on Windows, `%USERPROFILE%\.keel`):
conversations, settings, agent/workspace state and encrypted key material,
deliberately outside the application directory.

| Platform | Uninstall | `~/.keel` on uninstall |
|---|---|---|
| Windows | Run the uninstaller in the install directory (default under `%LOCALAPPDATA%`), or "Apps & features". | Preserved: `build.nsis.deleteAppDataOnUninstall = false` and the custom `afterRunUninstall` macro is a no-op ("~/.keel is user data: never delete it on uninstall"). |
| macOS | Delete `/Applications/Keel.app` (a PKG install may leave a receipt; use a package-uninstall tool if you want it removed). | Not touched by removing the app bundle. |
| Linux | `sudo apt remove keel` / `sudo dnf remove keel`. | Package managers do not remove home-directory data. |

Remove `~/.keel` only if you explicitly intend to erase all local Keel data.

**Evidence boundary:** "install, launch, reinstall, silent uninstall,
`~/.keel` preserved on Windows 11" is asserted in `common.WINDOWS_NOTES` and is
a design invariant backed by the NSIS settings above. The final operations
runbook reports the six clean-VM external checks (install, start, backend
shutdown, uninstall, upgrade/rollback, signed launch) as **UNVERIFIED on this
host**. Treat preservation as design + static evidence, not a freshly re-run
clean-VM acceptance test.

---

## 6. Verify what you downloaded

The release produces `RELEASE-SHA256SUMS.txt` (one lowercase
`<sha256>  <filename>` line per asset), a `RELEASE-MANIFEST.json` with
`bytes`/`sha256`/`url` per file, and a `download.json` whose channels carry
`size`, `sha256` and `verified_at`. The live `/download` page enables a control
only when all of those agree.

```powershell
# Windows (PowerShell)
Get-FileHash .\Keel-Setup-<version>.exe -Algorithm SHA256
```

```bash
# macOS
shasum -a 256 Keel-<version>-macos-arm64.pkg
# Linux
sha256sum Keel-<version>-linux-amd64.deb
```

Compare with the value shown on `/download` or in `RELEASE-SHA256SUMS.txt`;
case does not matter, bytes do.

**Optional release-signature check (only after the owner provisions a key):**

```bash
python -m keel.release verify --manifest release/download.json --public-key <PUBLIC_KEY_PEM>
python -m keel.release verify --manifest release/RELEASE-MANIFEST.json \
  --public-key <PUBLIC_KEY_PEM> --require-available
```

Without `--public-key`, `verify` checks size, SHA-256, HTTPS and format only:
it makes **no** signature claim. Keep three claims distinct:

1. **Build integrity** — local checksums / `keel.release integrity` (7/7 on the
   final-source Windows rebuild; `FINAL-RELEASE-OPERATIONS.md` §2).
2. **Release signature** — Ed25519 over manifest and each artifact; currently
   **owner-gated / absent**.
3. **OS signature and clean-VM UX** — Authenticode / Developer ID/notarization
   and real install-launch-uninstall runs; currently **not configured /
   unverified on this host**.

---

## 7. Owner actions required before this guide can point to a real download

1. Provision the Ed25519 release key pair (names in
   `keel/docs/release/SIGNING-PREPARATION.md`); add the CI `sign` job; pass
   `--signing-key` at build and `--public-key` at publish/verify.
2. Decide on OS code signing / notarization (Authenticode, Developer ID).
   SignPath Foundation is **not** eligible for proprietary software
   (Master Plan v6 §4.3 D3).
3. Configure `KEEL_DOWNLOAD_MANIFEST_URL` to a first-party, public,
   binaries-only HTTPS endpoint (G1/G3). The current default points at the
   **private** source repository, not a verified public endpoint.
4. Regenerate the site fallback manifest after packaging changes
   (`python -m keel.release fallback`) and have the lead copy it into
   `keel/site/download.json` (§8).
5. Authorize the version tag and publication. Until then keep the site's
   honest "no installer publicly available" state.

No license term changes here: Keel stays proprietary under D-037 and the
source repo stays private under D-036 (gate G1).

---

## 8. Reconciled caveat: stale committed fallback manifest

`keel/site/download.json` (Agent A's file) still lists the **old** artifacts:
macOS `Keel-0.1.1-macos-arm64.dmg` with DMG/ZIP alternatives, and a Linux
`AppImage` primary with DEB/RPM alternatives. The release generator now emits
PKG/DEB/RPM (`common.build_fallback_download_manifest`) and `packaging.py`
rejects archive advertising. The fallback is nevertheless **safe** because
every channel remains `available: false` with no URL — no wrong binary can be
downloaded — but its filenames and install text are misleading.

Resolution (owner/lead + Agent A; not performed here): run
`python -m keel.release fallback --out <temp>` and copy the output into
`keel/site/download.json` before any public release. Documentation records the
mismatch; it does not hand-edit another agent's source file or a generated
registry.

---

## 9. Evidence index

- `keel/desktop-app/package.json`, `keel/desktop-app/build/nsis-keel.nsh` —
  NSIS / PKG / DEB / RPM configuration and data preservation.
- `keel/src/keel/release/{common,build,publish,verify,signing,updater,packaging,cli}.py`
  — artifact naming, static packaging checks, checksums, publication gate,
  fallback generator and update primitives.
- `keel/site/download.json`, `keel/site/api/download-manifest.js`,
  `keel/site/ui/download.js`, `keel/site/ui/download-clone.js` — availability
  gating and platform detection.
- `keel/docs/release/SIGNING-PREPARATION.md`,
  `keel/docs/FINAL-RELEASE-OPERATIONS.md`, `keel/docs/HOSTING.md`,
  `keel/docs/internal/DISTRIBUTION-TRANSITION-RUNBOOK.md` — signing,
  verification and hosting truthfulness.
- `DECISIONS.md` D-036 / D-037 and `Keel_Master_Plan_v6.md` §0.1/§0.2
  (read-only canonical; not overridden).
