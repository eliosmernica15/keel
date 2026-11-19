# Keel — public hosting for installers

This document is the truthful state of how finished Keel installers reach users.

## Current state (2026-11-19, updated after CI fix)

**No public Keel installer is available today.** The intended distribution channel is a Keel-controlled object storage/CDN (Cloudflare R2 preferred), fed by GitHub Actions, surfaced on the official `/download` page.

What exists now:

- CI builds the installers on every push to `main` (workflow at `.github/workflows/build-desktop.yml`; the project lives in `keel/` inside the repository).
- Verified green run: `44431591087` (2026-11-19, commit `d584ae7`). Artifacts are attached to that workflow run only, **not publicly distributed**, retained until 2027-02-17:
  - `keel-windows` (~122 MB) — `Keel-Setup-0.1.0.exe`, sha256 `43a5eb7db968faa26561ad9df793882e7de89d1da74b68c627187be1bd3339bf`
  - `keel-macos` (arm64) — `Keel-0.1.0-macos-arm64.dmg` sha256 `38759134f6cf495dff7d67ea89b259cad4519a1d0ebe5c2da5691a30c870bdba`; `.zip` sha256 `e4216b36dbcdef9dbf106a3a03361e1c778904b6aca3cbdad051b515eba9312d`
  - `keel-linux` — `Keel-0.1.0-linux-x86_64.AppImage` sha256 `2661953bf1a0d5c92faa91f3ef5e263e1ccfa79015d786fde94fd78876208beb`; `Keel-0.1.0-linux-amd64.deb` sha256 `15f5db415248ef8d36687b224b19033568890bce67cbc52a5b06f3ad41b04b3e`
- Intel macOS: not built (runner is arm64). Linux: not install-tested on desktop hardware. Neither macOS nor Linux binary has been launched by a human yet.
- Local build that was install-tested on this machine: `C:\Users\Admin\Desktop\Claude clone\keel\dist\Keel-Setup-0.1.0.exe` (122 MB, sha256 `56731AE2820AA46BD9E54A9E5C7151AB965B53BC7282FCC02D3DA6F792E19DCE`). This is a **different build** than the CI artifact — CI rebuilt it.
- Nothing is published to GitHub Releases; `site/download.json` stays `available: false` everywhere until a hosted download is tested end to end.

## Intended pipeline

1. Developer pushes to `eliosmernica15/keel`
2. GitHub Actions (`.github/workflows/build-desktop.yml`) builds Windows, macOS, Linux installers
3. On tag pushes (`v*`), `prepare-installers` stages a combined `keel-installers` artifact with `RELEASE-SHA256SUMS.txt`
4. `upload-to-hosting` ships the artifacts to Keel-controlled storage — **only when the `R2_UPLOAD_ENABLED` repository variable is `true`** — using the secrets below
5. `site/download.json` and `/download` page are updated to the hosted URLs (real sizes/hashes), and a fresh production deploy is verified before `available: true`

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
2. In GitHub: `eliosmernica15/keel` → Settings → Secrets and variables → Actions:
   - **Secrets** (tab 1): `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET_NAME`
   - **Variables** (tab 2): `R2_UPLOAD_ENABLED` = `true`
   Never put these values in chat, issues, or commits.
3. Choose the public origin, e.g. `https://download.keel.app` (custom domain → R2 bucket, cached immutable; keep versioned objects for rollback).
4. Tell me the origin (not the secrets). I will tag a release (`v0.1.0`), watch the `prepare-installers` and `upload-to-hosting` jobs, then point `site/download.json` at the hosted objects with their real sizes/hashes, deploy, and test a public download on each platform before marking availability true.

Until all of that is done, every installer entry in `/download` remains "Not currently available". That is intentional.

AWS S3 equivalent (Option B): secrets `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`, `AWS_S3_BUCKET`; same `R2_UPLOAD_ENABLED` gate would need adapting (ask first).

## What I will NOT do

- Upload anything to public GitHub Releases
- Proxy installer downloads through untrusted CDNs
- Expose any secret in the repository, build logs, or chat
- Upload installer artifacts without your explicit confirmation of the hosting provider and credentials
