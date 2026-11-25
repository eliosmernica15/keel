# Smart Download, manifest contract, release pipeline and PWA behavior

**Owner:** Agent H (documentation). **Date:** 2026-11-25; reconciled with the
concurrent site/packaging changes in this worktree.
**Status:** descriptive of current code; implementation and evidence kept
distinct. Site files belong to Agent A and packaging to Agent E; discrepancies
recorded here are for the owning agents/lead to resolve, not silently patched
by documentation.

---

## 1. Smart Download — what actually runs

`keel/site/download.html` now loads **two** modules at the bottom:
`/ui/download-clone.js` (mega-menu, FAQ, mobile menu, chat, news, copy buttons,
footer search) and `/ui/download.js` (the manifest-driven download UX). The
legacy card DOM was replaced by
`<div id="kp-download-variants">`, a single primary action
`#kp-download-primary`, an "Other platforms" disclosure and an ARIA live status
`#kp-download-status`.

| Script | Manifest source order | Role |
|---|---|---|
| `/ui/download.js` (live download UX) | `/api/download-manifest`, then `/download.json` | Detects the platform, builds explicit variants, resolves a primary action and renders honest states. Exports pure helpers on `globalThis.__KEEL_DOWNLOAD__` for Node/Playwright tests. |
| `/ui/download-clone.js` | `/download.json`, then `/api/download-manifest` | Still initialises its own download bindings, but the `[data-channel]` / `#hero-download` elements it targeted were removed from `download.html`, so it no longer drives the primary download flow. |
| `/ui/landing-download.js` (landing page) | `/api/download-manifest`, then `/download.json` | Availability-driven hero CTA linking to `/download`, never directly to a binary. |

All sources are same-origin. A page takes the first response that is valid JSON
with a string `version` and an object `channels`; failures fall through to the
next source.

### 1.1 The availability gate

`isDownloadable(channel)` now requires **all** of:

```text
available === true
AND verified === true
AND verified_at present and matching ^\d{4}-\d{2}-\d{2}
AND size > 0
AND sha256 matching /^[0-9a-f]{64}$/i
AND safeUrl(url) !== null   // https:// only; loopback http for local development
```

`unavailableReason()` explains exactly which condition failed (missing
verification, missing timestamp/size/checksum/URL, or no build listed). A
control is never enabled because a build succeeded, and no URL/size/checksum is
invented. `safeUrl()` accepts loopback `http://localhost`, `127.0.0.1`, `[::1]`
only for local testing; the release pipeline never emits HTTP.

### 1.2 Variants and states

`variantsFor()` builds a deduplicated candidate list from the channel primary
plus its manifest `alternatives`, keyed as `windows:<arch>`,
`macos:<arch>` and `linux:<format>`. Every variant is rendered with its label,
version, size or reason, and a Download / Unavailable action.

`resolvePrimary()` is a pure decision function with explicit, testable states:

| State | Meaning |
|---|---|
| `detecting` / `detected` / `checking` | Platform detection or manifest fetch in progress. |
| `ready` | A verified, downloadable variant was selected; CTA becomes an `<a href>` with a checksum-verified title. |
| `arch-confirm` | Detected macOS, architecture unknown, more than one variant: "Choose Apple Silicon or Intel". No silent wrong-architecture pick. |
| `unavailable` | Manifest unavailable, no builds listed, or no variant passed the gate; CTA disabled with a reason. |
| `unsupported` | iOS, Android or Windows ARM: honest "not supported / not published" text in an ARIA live region. |
| `started` | User clicked a verified link; page reminds them to verify the SHA-256. |

Preference order when a choice is possible: macOS
`macos:arm64` / `macos:x64` by detected arch; Linux `linux:deb` →
`linux:rpm` → `linux:appimage`; Windows `windows:x64` (or arm64 when detected,
with a note that a native ARM build is not published). Selecting "Other
platforms" switches the active OS and re-runs the decision.

---

## 2. Platform detection and its limits

### 2.1 How detection works

- OS first: iOS (`iPhone|iPad|iPod` / `iPadOS|iOS` platform) and Android are
  detected before desktop platforms.
- Architecture only when the browser actually tells us:
  `navigator.userAgentData.getHighEntropyValues(["architecture","bitness","platform"])`
  (async), with the static `userAgentData.architecture` as a synchronous
  fallback; `arm`/`arm64`/`aarch64` → `arm64`, `x86` → `x64` by bitness.
- Windows falls back to `Win64|x64|WOW64` in the UA. macOS deliberately keeps
  arch unknown when hints are absent — the comment is explicit: "browsers do
  not reliably expose Intel vs Apple Silicon". Linux never guesses DEB vs RPM
  from the UA. Unknown platform → no OS, and the user picks from "Other
  platforms".

### 2.2 Limits that must be stated, not hidden

1. **Heuristic only.** `userAgentData` is Chromium-oriented; others fall back
   to UA strings that can be spoofed or stripped by privacy settings.
   Detection is a convenience, never a security or entitlement decision.
2. **High-entropy hints are permission/secure-context gated.** Failure sets
   `arch = null`; the page then asks the user instead of guessing.
3. **macOS architecture is not reliably detectable.** The `arch-confirm` state
   exists precisely because two real PKGs (arm64/x64) may exist and choosing
   wrongly would be harmful. This resolves the earlier "Intel unsupported"
   inconsistency: the page no longer declares Intel unsupported, it offers an
   explicit choice (§7).
4. **Linux package family is not detectable.** Explicit DEB/RPM variants come
   from the manifest, not the UA. The earlier "no family selector" gap is
   resolved in the live UX.
5. **Unsupported platforms are named, not silently filtered.** iOS, Android
   and Windows ARM get a truthful explanation; no installer is offered for
   them.
6. **Loopback HTTP exception** exists only for local development; production
   links are HTTPS-only, enforced by `safeUrl()` and by `verify.py`.

---

## 3. Manifest contract

Both documents are produced by `keel/src/keel/release/common.py`.

### 3.1 `download.json` (site-facing availability manifest)

```text
{
  name, version, tag, edition, generated ("fallback"|"release-pipeline"),
  published_at, verified_at, base_url, release_manifest_url,
  channels: {
    windows: { name:"Windows x64 (64-bit)", arch:"x64", version, file:"Keel-Setup-<version>.exe",
               size:int|null, sha256:string|null, url:https|null,
               available:bool, verified:bool, verified_at:string|null,
               notes, installation, alternatives:[] },
    macos:   { primary Keel-<version>-macos-arm64.pkg; alternatives: [ Keel-<version>-macos-x64.pkg ] },
    linux:   { primary Keel-<version>-linux-amd64.deb; alternatives: [ Keel-<version>-linux-x86_64.rpm ] }
  }
}
```

- `build_fallback_download_manifest(version, tag)` (new CLI subcommand
  `python -m keel.release fallback`) emits the honest fallback shape: no URL,
  size, hash or timestamp, all `available`/`verified` false. The lead copies its
  output into `keel/site/download.json`; the generator never writes there.
- `build_download_manifest(...)` emits the published shape with values from
  the actual artifacts and `url = <base_url>/<tag>/<quoted filename>`.
- `arch_for_artifact()` derives architecture from filenames so an Intel PKG is
  not mislabelled as arm64 in an alternative entry.
- **Availability rule (immutable):** `available=true` only when `url` is a real
  verified public HTTPS asset, `size`/`sha256` came from that file,
  `verified=true` and `verified_at` is set. Never fabricate.
- **Known inconsistency:** the currently committed `keel/site/download.json`
  still lists the previous DMG/ZIP/AppImage artifacts. It remains safe
  (all channels unavailable), but its filenames/install text are stale. See
  `DISTRIBUTION-INSTALLATION.md` §8.

### 3.2 `RELEASE-MANIFEST.json` (integrity / update manifest)

```text
{ name, version, tag, edition, generated, published_at,
  min_version, blocked_versions:[], security_advisories:{},
  rollout:{mode, percentage, bucket_count},
  files:[ {platform, arch, version, file, bytes, sha256, url} ],
  checksums_file:"RELEASE-SHA256SUMS.txt", signature?, signature_algorithm? }
```

Consumed by `updater.py` (signed-manifest check, `min_version`,
`blocked_versions`, rollout bucket) and
`verify_release_manifest()` (HTTPS download-back, size, SHA-256, optional
Ed25519 `<file>.sig` verification).

### 3.3 `RELEASE-SHA256SUMS.txt`

One lowercase `<sha256>  <filename>` line per staged installer, written at
build time and re-checked at publish time.

---

## 4. Release pipeline (as implemented)

Python-only (`python -m keel.release …`), CWD `keel/`.

1. **Version gate** — `python scripts/check_version_sync.py` (and `--tag` on a
   `v*` tag). `common.validate_version()` requires seven version sources to
   agree (`pyproject.toml`, `desktop-app/package.json`, `desktop-app/package-lock.json`,
   `site/download.json`, `desktop/src-tauri/tauri.conf.json`,
   `desktop/src-tauri/Cargo.toml`, `src/keel/__init__.py`); tag must be `v<version>`.
2. **Packaging preflight** — `build.py` calls
   `packaging.check_packaging_config()` and fails fast on config drift; it uses
   `npm ci` (lockfile integrity) instead of `npm install`, and runs
   `check_built_inventory()` after the build. Static checks are also exposed as
   `python -m keel.release check-packaging [--installer ...] [--dist ...] [--platform ...]`.
3. **Per-OS build** — PyInstaller sidecar, `electron-builder --publish never`
   with NSIS (Windows), PKG arm64/x64 (macOS), DEB/RPM (Linux). Stage flat into
   `release/`, write checksums and `RELEASE-MANIFEST.json`. Optional
   `--signing-key <Ed25519 PEM>` writes `<file>.sig` per artifact and signs the
   canonical manifest.
4. **Publish** (tags only, owner-authorized) — `publish.py` flattens/validates
   artifacts, and for any real publish (`dry_run == False`) **always enforces**:
   `verify_signed_release(root, public_key)` must succeed. Unsigned →
   `RELEASE SIGNING GATE FAILED`, non-zero exit. `--dry-run` stays unsigned-
   compatible unless `--require-signed` / `KEEL_REQUIRE_SIGNED=1`.
5. **Upload order** — find/create a draft GitHub Release, delete any old
   `download.json`; upload installers, checksums, release manifest and (when
   signed) `.sig` assets; make the release public; download every public URL
   back over HTTPS and compare size + SHA-256 (+ signatures).
6. **Availability gate** — only then write/upload `download.json`; re-fetch
   `https://github.com/<repo>/releases/latest/download/download.json`, compare
   parsed JSON byte-for-byte and re-verify files; delete the manifest asset on
   failure so the site cannot advertise an unverified release.
7. **Site** — Vercel serves the static site; `/api/download-manifest` proxies
   the manifest configured in `KEEL_DOWNLOAD_MANIFEST_URL`; the page falls back
   to committed `download.json`.

`verify` is available separately:
`python -m keel.release verify --manifest <path-or-url> [--compare <url>]
[--public-key <PEM>] [--require-available]`.

---

## 5. Public asset hosting and verification status

- **Code reality:** `common.py` defaults `base_url` to
  `https://github.com/<repo>/releases/download` with repo
  `eliosmernica15/keel`. Installers are GitHub Release assets; Vercel hosts the
  site and manifest proxy only.
- **Proxy:** GET-only, HTTPS-only, 256 KB cap, `no-store` upstream fetch,
  8 s timeout, JSON shape validation, 60 s public cache / 300 s stale-while-
  revalidate; 503 when `KEEL_DOWNLOAD_MANIFEST_URL` is unset, invalid or
  non-HTTPS. No credentials embedded.
- **Owner-gated target:** a first-party public binaries-only endpoint (G1/G3).
  The current default points at the **private** source repository, so it is
  not a verified public download endpoint. Until a real public HTTPS URL
  returns 200 and passes checksum verification the page must show "no installer
  publicly available". See `DISTRIBUTION-TRANSITION-RUNBOOK.md` / `HOSTING.md`.
- Vercel cannot host the installers directly (Hobby-plan 100 MB deployment cap;
  GitHub also rejects >100 MB files). No new storage provider was introduced.
- **Signing status:** unsigned / not notarized; no OS identity and no Ed25519
  release key on this host. See `release/SIGNING-PREPARATION.md`.

---

## 6. PWA behavior and contextual download link

- `keel/site/manifest.webmanifest` now declares `"id": "/app"`,
  `"start_url": "/app"`, `"scope": "/"` (previously `start_url: "/app.html"`).
  The installed PWA opens the **real application route**, never `/download`.
- It declares one shortcut: **"Get Keel Desktop"** →
  `https://keel-desktop.vercel.app/download` — the single in-app/PWA contextual
  link to the download page.
- `keel/site/vercel.json` rewrites `/app` → `/app.html` (and `/app/` →
  `/app.html`) and redirects `/app.html` → `/app`, with a `must-revalidate`
  header on `/app`. The earlier baseline defect (`/app` → `/download`) is
  **resolved in this source tree** — not re-tested on a live deployment.
- `keel/site/sw.js` is now `keel-shell-v17`. It precaches only `/app`, the app
  CSS/JS, manifest, icons and fonts. `NEVER_CACHE` explicitly excludes
  `/api/*`, `/download.json` and installer extensions
  (`.exe|.msi|.dmg|.pkg|.deb|.rpm|.AppImage|.zip|…`); `isCacheable()` further
  limits caching to the `SHELL` set, skips non-200 / `Content-Disposition`
  responses and cross-origin traffic, and supports `SKIP_WAITING`. Release
  metadata and binaries are never cached.
- `keel/site/ui/app.js` registers `/sw.js` and hides the in-app `#nav-download`
  link when running against the local bridge ("the bridge has no /download
  route … the download link is a dead end", `app.js:2049-2052`).

---

## 7. Reconciliation / open gaps (implementation vs evidence)

| # | Earlier observation | Current disposition |
|---|---|---|
| 1 | Manifest notes said Intel macOS was built while the old card UI said Intel unsupported. | **Resolved in UX**: `download.js` offers explicit arm64/x64 PKG variants and an `arch-confirm` state; no "Intel unsupported" claim. Still no public verified x64 asset. |
| 2 | Linux DEB vs RPM choice was missing. | **Resolved in UX**: manifest-derived `linux:deb` / `linux:rpm` variants with explicit selection; no UA guessing. |
| 3 | `/download` loaded `download-clone.js` only; SW cached `download.js`. | **Changed**: `download.html` loads both; `download.js` drives downloads. Clone's legacy download hooks no longer bind. |
| 4 | `HOSTING.md` said "no secrets required beyond GITHUB_TOKEN". | **Superseded**: real publish hard-gated on Ed25519 signatures. `HOSTING.md` §0 reconciled. |
| 5 | Committed `site/download.json` lists DMG/ZIP/AppImage. | **Stale, safe**: new generator emits PKG/DEB/RPM; all channels still unavailable so no wrong binary can be fetched. Regenerate + copy before release (Agent A / lead). |
| 6 | PWA `start_url` was `/app.html` with SW v16. | **Current**: `start_url /app`, SW v17, `Get Keel Desktop` shortcut to `/download`. Source-level only. |
| 7 | Sibling owner docs (security / QA / agent audit / provider audit) absent at first write. | QA E2E specs now landed in `keel/fleet-next/tests/distribution-qa/` (download, PWA, first-launch, landing, API, a11y); the QA *document* and the other three docs were still absent. No pass/fail inferred; lead to reconcile when they land. |
| 8 | No public HTTPS installer URL, no GitHub Release, no signing key, no native macOS/Linux GUI verification. | **BLOCKED / owner-gated.** Not production readiness. |

---

## 8. Evidence index

- `keel/site/download.html`, `keel/site/ui/{download-clone,download,landing-download}.js`,
  `keel/site/ui/download-ux.css`, `keel/site/download.json`,
  `keel/site/api/download-manifest.js`, `keel/site/vercel.json`,
  `keel/site/sw.js`, `keel/site/manifest.webmanifest`,
  `keel/site/ui/app.js`, `keel/site/app.html`.
- `keel/src/keel/release/{common,build,publish,verify,signing,updater,packaging,cli}.py`.
- Distribution QA specs: `keel/fleet-next/tests/distribution-qa/*.spec.ts`
  (present; results not asserted here).
- `keel/docs/DISTRIBUTION-BASELINE.md`, `HOSTING.md`,
  `FINAL-RELEASE-OPERATIONS.md`, `DISTRIBUTION-INSTALLATION.md`,
  `DISTRIBUTION-ARCHITECTURE.md`, `release/SIGNING-PREPARATION.md`,
  `internal/DISTRIBUTION-TRANSITION-RUNBOOK.md`.
