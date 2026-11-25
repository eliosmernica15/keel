# Production signing preparation (no credentials configured)

**Owner:** Agent H (documentation). **Updated:** 2026-11-25.
This document records the exact external credentials required before a Keel
release can be described as signed or trusted. No value exists in the current
environment; no fake certificate is generated and no unsigned package is
described as signed. Secret **names** only — never values.

## 1. Two different things called "signing"

| | Keel release signing | OS code signing / notarization |
|---|---|---|
| What | Ed25519 detached signatures for every installer (`<file>.sig`) and an embedded signature over the canonical `RELEASE-MANIFEST.json`. | Authenticode (Windows), Developer ID + notarization (macOS), optional provenance key (Linux). |
| Implemented in | `keel/src/keel/release/signing.py`; `build --signing-key`, `publish --public-key`, `verify --public-key`, `update-check`/`update-download`. | Not wired into CI. `electron-builder` reports "no code signing certificate configured, signing is skipped". |
| Why | Supply-chain integrity: proves artifacts were produced by the key holder and not altered. **Hard gate for every real publish.** | OS trust: removes SmartScreen / Gatekeeper warnings. Paid; excluded by the master plan unless the owner authorizes it. |
| Today | **Absent.** No key, no `.sig` assets, no signed manifest. | **Absent.** No PFX/p12, no Apple identity, no notarization. |
| Owner action | Generate/provision key pair outside the repo; add CI `sign` job; pass `--public-key` at publish/verify. | Purchase/provide certificates, store secrets, add signing jobs; decide on notarization. |

`publish.py` currently computes
`enforce_signing = (not dry_run) or require_signed_enabled(...)`. For a real
publish this is always true: without a supplied public key and valid
signatures the command prints `RELEASE SIGNING GATE FAILED` and exits non-zero.
A `--dry-run` can still be unsigned unless `--require-signed` or
`KEEL_REQUIRE_SIGNED=1` is set. `signing.py` explicitly refuses to generate a
production keypair; `generate_keypair()` is for ephemeral tests only.

## 2. Exact secret names required (names only)

Derived from `.github/workflows/signing-readiness.yml`, this file and
`keel/docs/FINAL-RELEASE-OPERATIONS.md` §3.

| Purpose | Secret name(s) | Source |
|---|---|---|
| Keel Ed25519 release signing (free path, recommended, hard gate) | `KEEL_RELEASE_SIGNING_KEY`, `KEEL_RELEASE_SIGNING_PUBLIC_KEY` | `signing.py`, `publish.py`, `master-plan-v6-release-acceptance.md` |
| Windows Authenticode | `WINDOWS_SIGNING_CERTIFICATE_BASE64` (PFX, base64), `WINDOWS_SIGNING_PASSWORD` | `signing-readiness.yml`, this file |
| macOS Developer ID + notarization | `MACOS_SIGNING_CERTIFICATE_BASE64` (p12, base64), `MACOS_SIGNING_PASSWORD`, `MACOS_NOTARIZATION_APPLE_ID`, `MACOS_NOTARIZATION_TEAM_ID`, `MACOS_NOTARIZATION_PASSWORD` (app-specific) | same |
| Linux provenance/integrity (optional) | `LINUX_SIGNING_KEY_BASE64`, `LINUX_SIGNING_PASSWORD` | this file |
| electron-builder aliases cited in existing evidence (paid paths currently excluded) | `CSC_LINK`, `CSC_KEY_PASSWORD`, `APPLE_ID`, `APPLE_APP_SPECIFIC_PASSWORD`, `APPLE_TEAM_ID` | `master-plan-v6-release-acceptance.md` |

`signing-readiness.yml` only prints `=CONFIGURED` / `=MISSING` for these names.
It never prints a value and never claims a package is signed. It is a
`workflow_dispatch` report, not a signing job. Observed GitHub Actions state in
the prior round: `total_count=0` (no secrets configured).

## 3. Per-platform verification once configured

- **Windows:** `signtool verify /pa /v <installer>`. Timestamping uses a public
  RFC 3161 server (no credential).
- **macOS:** `codesign --verify --deep --strict`, `spctl -a -vv`, and
  `xcrun stapler validate` on the notarized DMG.
- **Linux:** no platform-wide trusted identity is configured. Evidence is the
  committed `RELEASE-SHA256SUMS.txt`, `RELEASE-MANIFEST.json` and a signed
  release tag; if a key is configured, use `LINUX_SIGNING_KEY_BASE64` /
  `LINUX_SIGNING_PASSWORD`.
- **Release signing (all platforms):**
  ```bash
  python -m keel.release verify --manifest release/download.json --public-key <PUBLIC_KEY_PEM>
  python -m keel.release integrity --dist dist --artifacts release
  ```
  `verify` without `--public-key` checks only size / SHA-256 / HTTPS / format:
  it makes **no** signature claim.

## 4. Rules (unchanged)

- OS signing jobs must be **skipped, not failed**, when secrets are absent, and
  the release summary must state `unsigned`.
- The Ed25519 release gate is the opposite: a real publish must **fail closed**
  when the key or signatures are missing (`SigningGateError`).
- No release may be published as signed without a successful verification step
  for that platform.
- No development keypair may be generated as a fallback for release artifacts.
- Secrets are never echoed into logs, artifacts, chat or documentation.
- SignPath Foundation is **not** eligible for proprietary software
  (`Keel_Master_Plan_v6.md` §4.3 D3); a paid certificate is an owner decision.

## 5. Exact owner actions to unblock a signed release

1. **Ed25519 key pair.** Generate an Ed25519 keypair outside the repository
   and outside chat; store the private key as `KEEL_RELEASE_SIGNING_KEY` and
   the public key as `KEEL_RELEASE_SIGNING_PUBLIC_KEY` (or provide PEM files to
   CI). Never let the build generate it.
2. **CI `sign` job.** Add a job after the three per-OS builds and before
   `publish`; pass `--signing-key` to `python -m keel.release build`, fail fast
   when the key secret is absent, upload every `*.sig` and the signed
   `RELEASE-MANIFEST.json`, and make `publish` verify with the matching public
   key (`--public-key`, `KEEL_REQUIRE_SIGNED=1`).
3. **OS trust decision.** Decide whether to purchase an Authenticode
   certificate and a Developer ID/notarization subscription. If yes, create
   the five Windows/macOS secrets above and add the corresponding signing
   jobs; if no, keep shipping unsigned with documented SmartScreen / Gatekeeper
   steps and keep the release notes saying "unsigned".
4. **Optional Linux key.** If provenance signing is desired, create
   `LINUX_SIGNING_KEY_BASE64` / `LINUX_SIGNING_PASSWORD`.
5. **Public feed (G1/G3).** Configure `KEEL_DOWNLOAD_MANIFEST_URL` to a
   first-party, public, binaries-only HTTPS endpoint before publishing; the
   current default points at the private source repository.
6. **Authorization.** Approve the version tag, the push/merge of the branch
   and the first publication. No push, tag, secret write, signing or publication
   has occurred in this workstream.

## 6. Evidence index

`keel/src/keel/release/{signing,build,publish,verify,updater,cli}.py`,
`.github/workflows/signing-readiness.yml`, `.github/workflows/build-desktop.yml`,
`keel/docs/FINAL-RELEASE-OPERATIONS.md` §2–§3 and §8,
`keel/docs/DISTRIBUTION-INSTALLATION.md` §6–§7,
`keel/docs/DISTRIBUTION-ARCHITECTURE.md` DA-03,
`DECISIONS.md` D-036 / D-037 (read only),
`Keel_Master_Plan_v6.md` §0.1/§0.2/§4.3 (read-only canonical).
