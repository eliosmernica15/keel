# Distribution architecture decisions (additive; does not override prior decisions)

**Owner:** Agent H (documentation / architecture). **Date:** 2026-11-25.
**Status:** documentation of decisions already reflected in code and earlier
docs. It does **not** amend `DECISIONS.md` D-036 / D-037, the read-only
`Keel_Master_Plan_v6.md`, any generated registry, or any license term.

## 1. Purpose and precedence

This file records distribution-only decisions so the installation and Smart
Download guides have a stable rationale. Precedence, highest first:

1. Owner gates and standing instructions in `Keel_Master_Plan_v6.md` §0.1
   (source private, all visibility changes gated) and §0.2 (proprietary code).
2. `DECISIONS.md` D-036 (Y6.4 public-visibility row rejected) and D-037 (MIT on
   Keel code rejected; `THIRD_PARTY_NOTICES` only).
3. Shared contracts in `keel/docs/DISTRIBUTION-BASELINE.md`.
4. The decisions below, which are **consistent with 1–3** and add no new
   license grant, no visibility change and no production-readiness claim.

If a conflict is found, 1–3 win and this file must be corrected.

## 2. Decision register (distribution)

| ID | Decision | Rationale / evidence | State |
|---|---|---|---|
| DA-01 | Installers are GitHub Release assets; Vercel serves the site and a manifest proxy only. No new storage provider is introduced. | `HOSTING.md`; `release/common.py` default `base_url`; `site/api/download-manifest.js`. Final public endpoint is still owner-gated (G1/G3). | Implemented in code; **not** a live public feed. |
| DA-02 | Availability is evidence-gated: `available=true` only after a real public HTTPS download matches byte size and SHA-256, with `verified=true` and `verified_at` set. Compilation never implies availability. | `DISTRIBUTION-BASELINE.md` shared contract; `common.build_download_manifest`, `publish.py`, `verify.py`; site `isDownloadable`. | Implemented. |
| DA-03 | Keel **release signing** (Ed25519 detached signatures + canonically signed `RELEASE-MANIFEST.json`) is a hard publication gate for real publishes. OS **code signing/notarization** is a separate, paid, owner-gated trust path. Neither exists today. | `release/signing.py`, `publish.py` (`enforce_signing = not dry_run`), `release/SIGNING-PREPARATION.md`, `signing-readiness.yml`. | **BLOCKED** — owner key/credentials required. |
| DA-04 | Smart Download degrades honestly: OS/arch detection is best-effort; unsupported platforms are told why; no URL or checksum is fabricated; the user chooses macOS architecture and the Linux package family explicitly. | `site/ui/download.js` (`resolvePrimary`, `variantsFor`, `arch-confirm`), `landing-download.js`. | Implemented best-effort; the earlier Linux-family and Intel-macOS gaps are resolved in the live UX. No public verified asset yet. |
| DA-09 | The primary consumer path is a **native OS installer on every platform**: NSIS EXE (Windows), PKG for arm64 and x64 (macOS), DEB primary / RPM alternative (Linux). Archives (DMG/ZIP/AppImage) are not offered. | `desktop-app/package.json`, `release/common.CHANNELS`, `release/packaging.check_packaging_config()`, `release/build.py`. | Configured; PKG/DEB/RPM native builds not executed on this host. The committed fallback `site/download.json` still lists the old archive names (safe but stale). |
| DA-05 | User state in `~/.keel` survives install, reinstall, upgrade and uninstall. Application files may be replaced; user data is never deleted by the installer. | `build.nsis.deleteAppDataOnUninstall=false`, `nsis-keel.nsh` `afterRunUninstall` no-op, additive idempotent migrations, `DISTRIBUTION-TRANSITION-RUNBOOK.md` rollback rules. | Design + static evidence; clean-VM re-test unverified. |
| DA-06 | The service worker caches the app shell only. Release manifests (`/download.json`, `/api/*`) and installer binaries are never cached; cross-origin traffic is untouched. | `site/sw.js` v16. | Implemented. |
| DA-07 | Documentation keeps **implementation** separate from **evidence**: "built and checksummed" ≠ "signed" ≠ "clean-VM verified" ≠ "publicly available". No status is upgraded without an owner decision or a fresh check. | `FINAL-RELEASE-OPERATIONS.md`, `MASTER-PLAN-INVENTORY.md`, this file. | Applied throughout this round. |
| DA-08 | Package-manager/store distribution must accept proprietary freeware without requiring a public source manifest; AUR binary and self-hosted APT/YUM remain. No store is added until checked. | `DECISIONS.md` X0.5 resolution; `Keel_Master_Plan_v6.md` X0.5. | Recorded; not implemented. |

## 3. Explicit non-effects on prior decisions

- **D-036 (privacy / repository visibility).** Nothing here changes repo
  visibility or requests a GitHub setting change. A first-party **binaries-only**
  public endpoint is a separate owner-gated action (G1/G3); it does not expose
  source, internal docs, CI logs or credentials. The target order remains:
  public binary feed → website cutover → verify old clients → visibility
  change only with explicit owner approval.
- **D-037 (proprietary licensing).** Keel's own code and installers stay
  proprietary / all-rights-reserved. This architecture adds **no** MIT or other
  open-source grant to Keel code. Third-party components keep their own
  licenses, preserved in root `THIRD_PARTY_NOTICES.md` and
  `keel/docs/DEPENDENCY-LICENSE-INVENTORY.md`. The removed draft MIT `LICENSE`
  stays removed.
- **No generated file** (`PLAN-INDEX.json`, `parity.json`,
  `Keel_Master_Plan_v6.md`, plan sources) was edited or hand-edited.
- **No production-readiness claim.** DA-01…DA-08 describe contracts and code;
  owner/external gates (signing key, public feed, OS certificates, native
  macOS/Linux GUI verification, clean-VM tests, visibility/security settings)
  remain open.

## 4. Evidence index

`keel/docs/DISTRIBUTION-BASELINE.md`, `keel/docs/HOSTING.md`,
`keel/docs/DISTRIBUTION-INSTALLATION.md`,
`keel/docs/DISTRIBUTION-SMART-DOWNLOAD.md`,
`keel/docs/release/SIGNING-PREPARATION.md`,
`keel/docs/internal/DISTRIBUTION-TRANSITION-RUNBOOK.md`,
`keel/docs/FINAL-RELEASE-OPERATIONS.md`, root `DECISIONS.md` (read only),
root `Keel_Master_Plan_v6.md` (read-only canonical).
