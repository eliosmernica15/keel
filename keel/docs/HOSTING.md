# Keel — public hosting for installers

This document is the truthful state of how finished Keel installers reach users.

## 0. Reconciliation (2026-11-25 — authoritative over the 2026-11-19 snapshot below)

The 2026-11-19 section is preserved as history, but three of its statements are
now superseded by the code in this worktree:

1. **"No secrets are required beyond the automatic `GITHUB_TOKEN`" is stale.**
   `keel/src/keel/release/publish.py` now hard-gates every real publish on
   Ed25519 signatures: `enforce_signing = (not dry_run) or …`, and
   `verify_signed_release(root, public_key)` must succeed. Without an
   owner-supplied `--public-key` and valid `<file>.sig` assets plus a signed
   `RELEASE-MANIFEST.json`, publish fails with `RELEASE SIGNING GATE FAILED`.
   `GITHUB_TOKEN` is still the only *network* credential, but a release-signing
   key is now mandatory for a real publish. See
   `keel/docs/release/SIGNING-PREPARATION.md`.
2. **Native packages are now the primary path.** Concurrent packaging work
   changed `desktop-app/package.json` to `build.mac.target = pkg` for `arm64`
   and `x64` (install location `/Applications`, `overwriteAction: upgrade`) and
   `build.linux.target = [deb, rpm]` (no AppImage). `release/common.py`
   `CHANNELS` and `release/packaging.py` now mirror that and reject
   DMG/ZIP/AppImage advertising. The historical file table below (DMG/ZIP/
   AppImage/deb) describes the older 0.1.0 artifacts; it is not the current
   target. The committed `site/download.json` fallback is stale but safe (all
   channels unavailable). See `DISTRIBUTION-INSTALLATION.md` §1 and §8.
3. **GitHub Releases on the private source repo is not yet a public endpoint.**
   `KEEL_DOWNLOAD_MANIFEST_URL` is unset by default and the proxy returns 503;
   `site/download.json` is an honest all-unavailable fallback. A first-party,
   public, binaries-only endpoint and the `/download` cutover remain owner-gated
   (G1/G3). No release has been published, so there is no verified public URL.

Also resolved since the baseline: the PWA routing defect (see
`DISTRIBUTION-SMART-DOWNLOAD.md` §6) — `vercel.json` rewrites `/app` →
`/app.html` and redirects `/app.html` → `/app`; the manifest now uses
`"id": "/app"`, `"start_url": "/app"`, `"scope": "/"`, with a single
"Get Keel Desktop" shortcut to `/download`. The service worker is v17 and
never caches release metadata or installer binaries. This is a source-tree
observation, not a live deployment test.

**Bottom line:** the chosen architecture below (GitHub Releases + Vercel proxy +
Python-only automation) still describes the code, but a real publication is
blocked by the signing key and public-endpoint owner gates. Do not describe the
current state as a production release.

## Current state (2026-11-19 — historical snapshot; see §0)

Keel has **no third-party storage provider**. Installers are published as assets
of a GitHub Release attached to `github.com/eliosmernica15/keel`, and the Vercel
site only links to those assets. Release automation is Python-only:
`python -m keel.release build|publish|verify`.

What exists and is verified right now:

- CI builds Windows/macOS/Linux installers on every push; `validate-versions`
  gates builds on version consistency.
- The Python release manager (`keel/src/keel/release/`) builds, stages, hashes,
  publishes and verifies releases.
- The Vercel site reads `/api/download-manifest`, which proxies the latest
  GitHub Release's `download.json`. Availability flips without a website
  redeploy.
- `/download` and the landing page enable a button only when the manifest has
  `available: true`, an HTTPS URL, a positive byte size and a 64-hex SHA-256.
- `site/download.json` is an honest fallback manifest: all channels
  `available: false`, no URLs.

## Hosting investigation: Vercel

Vercel **cannot** host the installers directly. This project is on the **Hobby**
plan, and Vercel's static file upload limit is **100 MB per deployment** on
Hobby (1 GB on Pro). Every Keel installer is larger than that:

| File | Bytes |
|---|---|
| `Keel-Setup-0.1.0.exe` | 122,107,077 |
| `Keel-0.1.0-macos-arm64.dmg` | 130,643,141 |
| `Keel-0.1.0-macos-arm64.zip` | 126,655,463 |
| `Keel-0.1.0-linux-x86_64.AppImage` | 148,873,931 |
| `Keel-0.1.0-linux-amd64.deb` | 121,445,684 |

Total release size is about 649 MB, so even a single installer exceeds the
Hobby limit. Upgrading to Pro would raise the upload limit to 1 GB, but it would
still not solve the second blocker: **GitHub rejects files larger than 100 MB**,
so none of the five installers can be committed to the repository that Vercel
deploys from. Vercel has no supported way to deploy a 650 MB static bundle from
Git, and using `vercel deploy` of a 650 MB bundle on every release is not a
supported distribution channel. No workaround using another provider was added.

## Architecture chosen

- **GitHub Releases** (existing repository, no new service) hosts the five
  installers plus `RELEASE-MANIFEST.json`, `RELEASE-SHA256SUMS.txt` and
  `download.json`.
- **GitHub Actions** builds per-OS, then the publish job runs
  `python -m keel.release publish`, which creates the release, uploads every
  asset, verifies each public URL + size + SHA-256, and only then uploads
  `download.json`.
- **Vercel** hosts the website and `/api/download-manifest`, which proxies the
  latest release's `download.json`. No website redeploy is needed for a release.
- **Python** is the only release automation language.

## Pipeline

1. Push a version bump and tag `v<version>` (tag must match every version source).
2. `validate-versions` asserts version consistency.
3. `build-*` jobs run `python -m keel.release build`, producing the installer,
   checksums and a release manifest per platform.
4. The `publish` job (tags only) runs `python -m keel.release publish`:
   - stages all artifacts flat,
   - creates a draft GitHub Release for the tag,
   - uploads every installer, checksums and `RELEASE-MANIFEST.json`,
   - downloads every public asset over HTTPS and compares size + SHA-256,
   - generates and uploads `download.json` only after that verification,
   - publishes the release,
   - re-fetches `releases/latest/download/download.json`, compares it byte-for-byte
     (parsed JSON) to the generated manifest and re-verifies every file.
5. `python -m keel.release verify` is the verification step.
6. The Vercel function `/api/download-manifest` serves the latest manifest.

Packaging always runs with `--publish never`; GitHub Releases are created only by
the Python publish step.

## Commands

```
python -m keel.release build      # build installers for the current OS
python -m keel.release publish    # publish a verified release to GitHub Releases
python -m keel.release verify     # verify a release manifest and its files
```

## What is missing today

Nothing in the repository; a release requires a new version tag because the
existing `v0.1.0` tag points at an older commit (`f2aba1d`). To publish:

1. Bump the version in `pyproject.toml`, `desktop-app/package.json`,
   `desktop-app/package-lock.json`, `desktop/src-tauri/tauri.conf.json` and
   `site/download.json`.
2. Commit and push.
3. Create and push a new tag, e.g. `v0.1.1`. Do not move a published tag.
4. Watch the tag run. `publish` uploads, verifies and publishes the manifest.
   If any file, checksum or public read fails, the job fails and no manifest is
   published.

`GITHUB_TOKEN` is the only network credential; a real publish additionally
requires the owner-supplied Ed25519 signing key and matching public key
(§0 and `keel/docs/release/SIGNING-PREPARATION.md`). Without them the publish
step fails closed.

## What this pipeline will NOT do

- Introduce Cloudflare, AWS, S3, R2, Vercel Blob, Firebase, Supabase or any other
  storage provider.
- Commit enormous binary files to Git.
- Proxy installer downloads through untrusted CDNs.
- Expose any secret in the repository, build logs, or chat.
- Mark a channel available because it compiled. Availability requires a real
  public HTTPS download whose SHA-256 matched.
- Claim the installers are signed or notarized. They are not.
