# Keel — public hosting for installers

This document is the truthful state of how finished Keel installers reach users.

## Current state (2026-11-19)

**No public Keel installer is available today.** The distribution channel is
Keel-controlled object storage (Cloudflare R2), fed by GitHub Actions and
surfaced on the official `/download` page. The pipeline is implemented and
tested, but it cannot publish until the storage account and repository
settings exist.

What exists and is verified right now:

- CI builds Windows/macOS/Linux installers on every push; `validate-versions`
  gates builds on version consistency (pyproject == package.json ==
  package-lock == tauri.conf == site/download.json, and tag == `v<version>`).
- **Installer validation performed (run `44527352992`, commit `c41372b`):**
  - Windows: hash-verified download; **silent install → launch → frozen Python
    sidecar on 127.0.0.1:8857 → bridge `403 refused` (token-protected) + static
    `/ui/style.css` 200 → reinstall → silent uninstall → `~/.keel` fully
    preserved** (marker file + `fleet.db` + `settings.json` intact). Real
    verification on Windows 11.
  - macOS: dmg/zip built in CI; hashes known (`fd334261…` dmg, `8adf5ceb…`
    zip) and **hash-verified locally**; zip structure inspected (619 entries;
    `Keel.app` bundle; Mach-O 64-bit binaries; frozen PyInstaller sidecar at
    `Contents/Resources/keel/keel`; Info.plist sane — `app.keel.desktop`,
    v0.1.0, LSMinimumSystemVersion 12.0); **unsigned — no `_CodeSignature`**;
    never mounted on a Mac; Intel unsupported by this build.
  - Linux: hash-verified downloads; `.deb` structure-inspected (control
    `Depends: libgtk-3-0, libnss3, libasound2`; `/opt/Keel` layout;
    `/usr/share/applications/keel-desktop.desktop`; postinst
    `update-alternatives` symlink; AppArmor handling on Ubuntu 24+); AppImage
    is ELF x86-64 type 2 with squashfs payload at offset 32609; **not launched
    on desktop Linux**.
- Artifacts are GitHub Actions workflow artifacts (90-day retention for the
  combined set), **not public releases**, not hosted anywhere.
- `site/download.json` is an honest fallback manifest: all channels
  `available: false`, no URLs. `/download` renders "Not currently available".
- The release workflow now stages a flat artifact set, uploads to R2 under
  `v<tag>/`, **downloads every public object over HTTPS and compares size and
  SHA-256**, then generates and publishes `download.json` last.
- The site reads `/api/download-manifest`, a same-origin Vercel function that
  proxies the published R2 manifest, and falls back to the committed
  `/download.json`. The landing page and `/download` only enable a button when
  the manifest has `available: true`, an HTTPS URL, a positive byte size and a
  64-hex SHA-256.
- Unsigned everywhere: SmartScreen (Windows), Gatekeeper (macOS), distro
  policy (Linux) will warn/block until certificates exist.

## Pipeline (implemented)

1. Developer pushes a version bump to `eliosmernica15/keel` and tags it
   `v<version>` (the tag must match every version source).
2. `validate-versions` asserts version consistency; the three build jobs produce
   Windows `.exe`, macOS `.dmg` + `.zip`, Linux `.AppImage` + `.deb`. Packaging
   always runs with `--publish never`; GitHub Releases are never created.
3. `prepare-installers` (tags only) requires all five files, stages them into a
   **flat** directory, writes `RELEASE-SHA256SUMS.txt`, and generates
   `RELEASE-MANIFEST.json` (platform, arch, file, bytes, SHA-256, URL).
4. `upload-to-hosting` runs **only** when the tag build succeeds, the repository
   variable `R2_UPLOAD_ENABLED` is `true`, and every R2 setting is present. It
   uploads to `s3://<bucket>/<tag>/<file>` with immutable caching.
5. It then downloads every public file over HTTPS and fails the job on any
   status, byte-count or SHA-256 mismatch.
6. Only after that verification, `make_download_manifest.py` builds
   `download.json` (all channels, alternatives, sizes, hashes, install notes).
   It is published to `<public-base>/download.json` and
   `<public-base>/<tag>/download.json`, re-fetched, compared byte-for-byte
   (parsed JSON) and fully re-verified.
7. The Vercel function `/api/download-manifest` serves the R2 manifest to the
   site. No website redeploy is needed for a new release; the manifest URL is
   public, non-secret configuration.

Scripts:

- `scripts/make_release_manifest.py` — per-file CI release manifest.
- `scripts/make_download_manifest.py` — site manifest; refuses incomplete
  releases and non-HTTPS base URLs.
- `scripts/verify_public_release.py` — real public download + size/SHA-256
  check.
- `scripts/check_download_manifest.py` — validates a published manifest and
  optionally compares it to the generated one.

## Exactly what is missing today

Nothing in the repository; this is account configuration only:

| Kind | Name | Value |
| --- | --- | --- |
| GitHub secret | `R2_ACCOUNT_ID` | Cloudflare account ID |
| GitHub secret | `R2_ACCESS_KEY_ID` | R2 API token access key |
| GitHub secret | `R2_SECRET_ACCESS_KEY` | R2 API token secret |
| GitHub secret | `R2_BUCKET_NAME` | e.g. `keel-releases` |
| GitHub variable | `R2_UPLOAD_ENABLED` | `true` |
| GitHub variable | `R2_PUBLIC_BASE_URL` | e.g. `https://download.keel.app` |
| Vercel env (public) | `KEEL_DOWNLOAD_MANIFEST_URL` | optional; defaults to `https://download.keel.app/download.json` |

`gh secret list` and `gh variable list` are empty, and the Vercel project has
no environment variables. No installer can become public until the first six
exist. Do not paste secret values into chat, issues, commits or logs.

## Setup (no secrets in this repository)

1. **Create the bucket.** Cloudflare dashboard → R2 → Create bucket
   `keel-releases`. Keep the bucket private; only the release prefix is served.
2. **Create a scoped token.** R2 → Manage R2 API Tokens → Create token →
   Object Read & Write, limited to `keel-releases`. This yields the access key
   ID and secret. The account ID is on the R2 overview page.
3. **Expose a public origin.** Preferred: R2 → bucket → Settings → Custom
   Domains → `download.keel.app` (DNS managed by Cloudflare). The bucket's
   `pub-<hash>.r2.dev` URL also works for testing but is rate-limited and not
   recommended for production. The origin must be HTTPS.
4. **Add GitHub configuration** in
   `https://github.com/eliosmernica15/keel/settings/secrets/actions`:
   - Secrets: `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`,
     `R2_BUCKET_NAME`
   - Variables: `R2_UPLOAD_ENABLED=true`,
     `R2_PUBLIC_BASE_URL=https://download.keel.app`
5. **Tell Vercel the manifest origin** (only if it is not
   `https://download.keel.app`): project `keel-desktop` → Settings →
   Environment Variables → `KEEL_DOWNLOAD_MANIFEST_URL =
   https://<public-origin>/download.json` for Production. This is public data.
6. **Release a new version.** The existing `v0.1.0` tag points at an older
   commit (`f2aba1d`), so the hardened workflow will not run for it. Bump the
   version in every source (`pyproject.toml`, `desktop-app/package.json` +
   lock, `tauri.conf.json`, `site/download.json`) and push a new tag, e.g.
   `v0.1.1`. Do not move a published tag.
7. **Watch the tag run.** `Publish verified installers` uploads, verifies and
   publishes the manifest. If any file, checksum, setting or public read
   fails, the job fails and no manifest is published.

Until all of that is done, every installer entry in `/download` remains "Not
currently available". That is intentional.

## What this pipeline will NOT do

- Upload anything to public GitHub Releases.
- Proxy installer downloads through untrusted CDNs.
- Expose any secret in the repository, build logs, or chat.
- Mark a channel available because it compiled. Availability requires a real
  public HTTPS download whose SHA-256 matched.
- Claim the installers are signed or notarized. They are not.
