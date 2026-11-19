# Keel — public hosting for installers

This document is the truthful state of how finished Keel installers reach users.

## Current state (2026-11-19)

**No public Keel installer is available today.** The intent is for the official Keel landing page to host the installers (`/download` route), fed by a private GitHub Actions pipeline producing artifacts and uploading them to Keel-controlled object storage/CDN.

Current assets:

- Local build: `C:\Users\Admin\Desktop\Claude clone\keel\dist\Keel-Setup-0.1.0.exe`
  - 122 MB
  - SHA-256: `56731AE2820AA46BD9E54A9E5C7151AB965B53BC7282FCC02D3DA6F792E19DCE`
  - Locally tested: silent install, launch, working bridge, silent uninstall
- macOS / Linux: **no artifacts exist yet.** CI workflows are present but have not produced or been tested on those platforms.

## Intended pipeline

1. Developer pushes to `eliosmernica15/keel`
2. GitHub Actions (`.github/workflows/build-desktop.yml`) builds Windows, macOS, Linux installers
3. Artifacts are uploaded to Keel-controlled storage (see below)
4. `site/download.json` and `/download` page reflect hosted versions

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

## Secrets to provide

Please provide **exactly one option** (A or B) and the corresponding credentials via **GitHub Secrets**, not in chat:

- Cloudflare R2: `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET_NAME`
- AWS S3: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`, `AWS_S3_BUCKET`

And the public origin where installers will be served, e.g.:

- `https://download.keel.app`
- or another domain we control

Once those are set, I can add the upload step to `.github/workflows/build-desktop.yml`, and flip `site/download.json` to reference the hosted URLs with real sizes/hashes.

## What I will NOT do

- Upload anything to public GitHub Releases
- Proxy installer downloads through untrusted CDNs
- Expose any secret in the repository, build logs, or chat
- Upload installer artifacts without your explicit confirmation of the hosting provider and credentials
