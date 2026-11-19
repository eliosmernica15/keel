# Keel — public hosting for installers

This document is the truthful state of how finished Keel installers reach users.

## Current state (2026-11-19, after release-pipeline hardening)

**No public Keel installer is available today.** The intended distribution channel is a Keel-controlled object storage/CDN (Cloudflare R2 preferred), fed by GitHub Actions, surfaced on the official `/download` page.

What exists and is verified right now:

- CI builds Windows/macOS/Linux installers on every push; `validate-versions` gates builds on version consistency (pyproject == package.json == package-lock == tauri.conf == site/download.json, and tag == `v<version>`).
- **Installer validation performed (run `44527352992`, commit `c41372b`):**
  - Windows: hash-verified download; **silent install → launch → frozen Python sidecar on 127.0.0.1:8857 → bridge `403 refused` (token-protected) + static `/ui/style.css` 200 → reinstall → silent uninstall → `~/.keel` fully preserved** (marker file + `fleet.db` + `settings.json` intact). This is real verification on Windows 11.
  - macOS: dmg/zip built in CI; hashes known (`fd334261…` dmg, `8adf5ceb…` zip) and **hash-verified locally**; zip structure inspected (619 entries; `Keel.app` bundle; Mach-O 64-bit binaries; frozen PyInstaller sidecar at `Contents/Resources/keel/keel`; Info.plist sane — `app.keel.desktop`, v0.1.0, LSMinimumSystemVersion 12.0); **unsigned — no `_CodeSignature`**; never mounted on a Mac; Intel unsupported by this build.
  - Linux: hash-verified downloads; `.deb` structure-inspected (control `Depends: libgtk-3-0, libnss3, libasound2`; `/opt/Keel` layout; `/usr/share/applications/keel-desktop.desktop`; postinst `update-alternatives` symlink; AppArmor handling on Ubuntu 24+); AppImage is ELF x86-64 type 2 with squashfs payload at offset 32609; **not launched on desktop Linux**.
- Artifacts are GitHub Actions workflow artifacts (90-day retention for the combined set), **not public releases**, not hosted anywhere.
- `site/download.json` documents the `44527352992` artifacts with real sizes/hashes; `available` is `false` everywhere. `/download` renders "Not currently available".
- Unsigned everywhere: SmartScreen (Windows), Gatekeeper (macOS), distro policy (Linux) will warn/block until certificates exist.

## Intended pipeline

1. Developer pushes to `eliosmernica15/keel`
2. `validate-versions` asserts version consistency; then GitHub Actions (`.github/workflows/build-desktop.yml`) builds Windows/macOS/Linux installers
3. On tag pushes (`v*`), `prepare-installers` re-checks versions against the tag, stages a combined `keel-installers` artifact with `RELEASE-SHA256SUMS.txt` and generates `RELEASE-MANIFEST.json` (platform, arch, file, bytes, sha256, URL or "pending" when no public base URL is configured)
4. `upload-to-hosting` ships to Keel-controlled R2 under `s3://<bucket>/<tag>/<file>` — **only when the `R2_UPLOAD_ENABLED` repository variable is `true`** — then **verifies every public HTTPS download and fails the tag release on any checksum mismatch**
5. `site/download.json` and `/download` are updated to the hosted URLs (real sizes/hashes), a fresh deploy is verified, and availability flips to `true` only after a tested public download

## Recommended hosting

### Option A: Cloudflare R2 (preferred)

- Solid object store for static files
- Free egress globally (if we subscribe through Cloudflare)
- Can front with a CDN via Cloudflare for performance
- Integrates with existing website Cloudflare config if used
- Storage classes configurable; can use same bucket for source assets and release artifacts

Required (one-time):

- Cloudflare account with R2 access
- R2 bucket for Keel releases: e.g. `keel-releases`
- Prefix: `{version}/…`
- Object keys:
  - `v0.1.0/Keel-Setup-0.1.0.exe`
  - `v0.1.0/Keel-0.1.0-macos-arm64.dmg`
  - `v0.1.0/Keel-0.1.0-linux-x86_64.AppImage`
  - plus `checksums.txt`, `RELEASE-NOTES.md`
- API token scoped to the single bucket, stored as GitHub Secrets: `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET_NAME`
- Custom domain (or subdomain) served by Cloudflare, e.g. `download.keel.app`
- CDN cache rules: long `Cache-Control` for immutable versioned files
- Retention policy: keep every versioned object; no overwrite

### Option B: Amazon S3 + CloudFront

- Mature, cost-effective, well documented for this exact pattern
- Integrates with AWS infra if any
- More steps for static-file serving, CORS, and CDN rules

Required:

- AWS account and IAM user with S3 + CloudFront access
- S3 bucket for releases: e.g. `keel-releases`
- CloudFront distribution or S3 static-website URL
- Object keys identical to Option A
- AWS secrets via GitHub Actions: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`, `AWS_S3_BUCKET`

## Secrets to provide (and how, safely)

1. Create the bucket and a scoped API token (Cloudflare dashboard → R2 → bucket `keel-releases` → Manage R2 API Tokens → Object Read & Write, scoped to that bucket only).
2. Public access: either a custom domain (R2 → bucket → Settings → Custom Domains, e.g. `download.keel.app`, with DNS you control) or the bucket's public `r2.dev` subdomain (fine for testing, not for production). Never make the bucket listing public; keep keys named `v<tag>/<file>` and mirror `s3://…/v<tag>/RELEASE-MANIFEST.json`.
3. In GitHub: `eliosmernica15/keel` → Settings → Secrets and variables → Actions:
   - **Secrets** (tab 1): `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET_NAME`
   - **Variables** (tab 2): `R2_UPLOAD_ENABLED` = `true`, `R2_PUBLIC_BASE_URL` = `https://download.keel.app`
   Never put these values in chat, issues, or commits.
4. Tell me the public origin (e.g. `https://download.keel.app`) and nothing else. Then I tag `v0.1.0`; the pipeline builds, the tag run stages the combined artifact and the release manifest, `upload-to-hosting` uploads under `v0.1.0/` and **verifies the public downloads over HTTPS** (any mismatch fails the tag).
5. Only after that verification passes do I update `site/download.json` and flip availability per platform.

Until all of that is done, every installer entry in `/download` remains "Not currently available". That is intentional.

AWS S3 equivalent (Option B): secrets `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`, `AWS_S3_BUCKET`; same `R2_UPLOAD_ENABLED`/`R2_PUBLIC_BASE_URL` variables would need adapting (ask first).

## What I will NOT do

- Upload anything to public GitHub Releases
- Proxy installer downloads through untrusted CDNs
- Expose any secret in the repository, build logs, or chat
- Upload installer artifacts without your explicit confirmation of the hosting provider and credentials
