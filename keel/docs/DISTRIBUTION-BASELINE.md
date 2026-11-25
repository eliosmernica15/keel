# Distribution baseline and shared contracts (lead, 2026-11-25)

## Baseline state
- Worktree: `C:\Users\Admin\Desktop\keel-frontend-worktree`; branch `feat/frontend-completion-2026-11-24`.
- PR #16 open (draft) against `main`; `origin/main` at `9a63be9` before this round.
- Divergence resolved: merged `origin/main` into the feature branch as `c80c2e1` (both ledgers preserved). All prior frontend, Electron-packaging and security work survived (verified by source checks).
- Source repo remains private; no visibility or security-setting changes.
- Marketing homepage must remain byte-identical; only `/download` and in-app/PWA contextual links may change.

## Existing implementation
- `site/download.html`, `site/ui/download.js`, `site/download.json` (fallback manifest: all channels `available:false`, `verified:false`, no URLs).
- `site/api/download-manifest.js`: GET-only HTTPS proxy, 256 KB cap, JSON validation, no credentials; returns 503 when `KEEL_DOWNLOAD_MANIFEST_URL` is unset.
- `site/vercel.json`: `/download` → `/download.html`; **`/app` and `/app.html` redirect to `/download`** — confirmed PWA routing defect to fix.
- Electron: `desktop-app/main.js` now prefers full local `desktop/ui`; `site` mirror reachable only via `KEEL_UI_PROFILE=mirror` or explicit `KEEL_UI_DIR`. Packaged Windows NSIS EXE built and launched in the previous round.
- Release manager under `src/keel/release/`; existing signing, manifest verification and publish modules must be reused.

## Shared contracts (immutable unless lead approves a change)

### Manifest schema (Agent E owns; Agent A consumes)
Compatible extension of `site/download.json`:
```
{ name, version, tag, generated, published_at, verified_at, base_url,
  release_manifest_url,
  channels: {
    windows: { name, arch:"x64", version, file:"Keel-Setup-<version>.exe",
               size:int|null, sha256:string|null, url:https|null,
               available:bool, verified:bool, verified_at:string|null,
               notes, installation, alternatives:[] },
    macos:   { primary PKG per arch (arm64/x64 or universal), alternatives:[] },
    linux:   { primary DEB or RPM, arch:"x86_64", alternatives:[ other family ] }
  }
}
```
Availability rule: `available=true` ONLY when `url` is a real verified public HTTPS asset, `size` and `sha256` are populated from the downloaded file, `verified=true`, and `verified_at` is set. Never fabricate.

### Platform IDs / selection
- IDs: `windows`, `macos`, `linux`; arches: `x64`, `arm64`, `x86_64`.
- Detect OS from `navigator.userAgentData?.platform` / `navigator.platform` / UA with safe fallbacks.
- Architecture only when reliable; macOS may offer explicit Apple Silicon / Intel choice; Linux must offer explicit DEB vs RPM choice (no guessing).
- Primary action downloads the selected primary channel; user gesture required.

### PWA contract
- Installed PWA start URL must open the real application route, never `/download`.
- In-app/PWA contextual link target: `https://keel-desktop.vercel.app/download` (one location only).
- Service worker caches app shell only; never installer binaries or release manifests beyond a short revalidated TTL.

### Verification criteria
- Build, checksum, download-back, checksum compare, release-signature verify, OS-signature status (truthful), install/launch, onboarding, uninstall/data preservation, public URL HTTPS 200.
- Native CI runners required per OS; publish only verified assets.

## Ownership summary
A: site download UI + PWA routing/registration. B: webapp.py only for proven defects + own test files. C: read-only agent audit + own tests. D: providers + own tests. E: desktop-app, release modules, release workflows, packaging doc. F: security tests/docs. G: E2E/a11y QA docs. H: all other docs/notices. Lead: integration, conflicts, commits, PR, merge.
