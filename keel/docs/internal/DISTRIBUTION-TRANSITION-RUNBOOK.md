# Distribution transition runbook (preparation only)

**Status: PREPARATION. Nothing here has been executed. G1/G3 approval required.**

## Current state (verified)

- Source repository: `https://github.com/eliosmernica15/keel` — public today.
- Website: `keel-desktop.vercel.app`; static site source in `keel/site/`.
- Public-facing site currently links to the source repo and internal docs:
  `site/index.html`, `site/app.html`, `site/ui/app.js`.
- Download manifest fallback: `site/download.json` currently has
  `"generated": "fallback"`, no `base_url`, no `url` values, and notes
  "Not publicly hosted, so there is nothing to download yet."
- Download manifest proxy: `site/api/download-manifest.js` defaults to
  `https://github.com/eliosmernica15/keel/releases/latest/download/download.json`.
- Release manager default download base:
  `src/keel/release/common.py` → `https://github.com/<repo>/releases/download`.
- Packaged Electron metadata: `resources/app-update.yml` points to GitHub
  provider `eliosmernica15/keel`. There is **no in-app updater implementation**
  in `desktop-app/main.js`; this is electron-builder metadata only.
- Old installers v0.1.0/v0.1.1 were built with GitHub-oriented URLs. There is no
  evidence that any public binary has been published (site says none hosted).

## Compatibility risk

If the source repository becomes private before a public binaries-only feed
exists:

1. Any existing client that reads GitHub Releases metadata or download URLs
   loses its update/download source.
2. `site/api/download-manifest.js` fails to fetch its default manifest.
3. `site/download.json` still contains internal CI notes and stale 0.1.0
   installation text; it must be sanitized before being public-facing.
4. `resources/app-update.yml` remains a stale GitHub pointer in already shipped
   installers and cannot be changed remotely.

Therefore the order is: **public binary feed first, website cutover, verify old
clients, then visibility change (G1)**. Publishing the first binary from the new
endpoint is separately gated by G3.

## Target architecture

- Private source repository (G1, not executed).
- Separate public binaries-only repository or equivalent static endpoint
  (default name `keel-releases`), containing only:
  installers, `.blockmap` files, `RELEASE-SHA256SUMS.txt`,
  `RELEASE-MANIFEST.json`, signed manifest/detached signatures, release notes,
  and `download.json`.
- Official website as the user-facing download interface; users never see the
  source repo URL.
- No source archives, CI logs, internal docs, research captures or credentials.

## Required mechanisms before first public release (G3)

1. Host the static endpoint with a first-party domain rewrite (for example
   `downloads.keel-desktop.vercel.app` → binaries-only repo/static host).
2. Replace `DEFAULT_MANIFEST_URL` in `site/api/download-manifest.js` with the
   first-party URL. Remove source-repo links from `site/index.html`,
   `site/app.html`, `site/ui/app.js` and `site/ui/download.js`.
3. Remove `repository` metadata from `desktop-app/package.json` (done in M1) and
   review `resources/app-update.yml` metadata before any new build.
4. Add owner-held Ed25519/minisign-style signatures for every artifact and the
   release manifest; embed the public key in the app and verify before install.
5. Keep SHA-256 checksums; enforce monotonic versions and an atomic/rollback
   install path. Existing `release/verify.py` covers HTTPS/size/SHA-256 only.
6. Sanitize `site/download.json`; remove CI run notes, stale instructions and
   `__hosting__` internal text.

## Rollback strategy

- Keep the previous installer and manifest on the public endpoint.
- Website manifest must be able to revert to the previous version.
- Installers must preserve `~/.keel` data on install/reinstall/uninstall.
- If verification fails, stop publication before downloading; never ship an
  unverified manifest.

## Migration sequence (owner approval at G1/G3)

1. Finish proprietary notice/docs and artifact allowlisting (M1).
2. Create/configure the public binaries-only endpoint; do not publish binaries.
3. Change website manifest source to the new endpoint; keep old fallback until
   verified.
4. Build and verify a release entirely through the new endpoint.
5. Obtain G3 approval; publish the first public binary.
6. Verify downloads, checksums, signatures and old-client behavior.
7. Only then request G1 approval to make the source repo private.
8. Monitor for stale GitHub links and update any cached docs/downloads.

## Status

Not executed. No endpoint created, no visibility changed, no release published.
