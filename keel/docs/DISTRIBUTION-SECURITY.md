# Distribution security — independent trust review (Agent F, 2026-11-25)

Scope: `site/api/download-manifest.js`, `site/sw.js`, `site/ui/download.js`,
`site/download.html`, `site/download.json`, `desktop-app/**`,
`src/keel/release/**`, `.github/workflows/**`. Baseline contracts from
`docs/DISTRIBUTION-BASELINE.md` and `docs/internal/DEFENSIVE-PATTERNS.md`.

This is a read-only review plus three new test files. No application, site,
release or workflow source was changed, no control was weakened, and no commit
or push was made.

Note: `site/ui/download.js` and `site/sw.js` were rewritten by another agent
during this review. Findings reference the versions current at the time of
sign-off (download.js IIFE exporting `__KEEL_DOWNLOAD__`; sw.js v17 with
`CACHEABLE` / `NEVER_CACHE`). The tests deliberately exercise exported behavior
and security invariants rather than brittle exact source strings, but the lead
should re-run them after any further UI changes.

## Commands and results (exact)

Environment: worktree `C:\Users\Admin\Desktop\keel-frontend-worktree`.

```
python --version                      -> Python 3.11.9
node --version                        -> v24.22.2
python -c "import cryptography; print(cryptography.__version__)" -> 50.0.1

cd C:\Users\Admin\Desktop\keel-frontend-worktree\keel
python -m pytest -q \
  tests/verify_distribution_security_manifest.py \
  tests/verify_distribution_security_pipeline.py \
  tests/verify_distribution_security_desktop.py
-> 41 passed, 7 xfailed in 12.47s

python -m pytest -q -rxX <same three files>
-> 41 passed, 7 xfailed; each xfail carries its SEC-F id and file:line reason
```

The proxy and download-page tests execute the **real** JS under Node with a
mocked `fetch` / exported pure API — no network and no browser build step.
Release tests use ephemeral Ed25519 keys and temporary files.

New files (exclusive ownership):

- `keel/tests/verify_distribution_security_manifest.py`
- `keel/tests/verify_distribution_security_pipeline.py`
- `keel/tests/verify_distribution_security_desktop.py`
- `keel/docs/DISTRIBUTION-SECURITY.md` (this file)

## Control-by-control acceptance

| # | Control | Verdict | Evidence |
|---|---|---|---|
| 1 | Manifest proxy: GET-only, HTTPS-only upstream, URL validation, size cap, JSON validation, cache controls, no credentials, no arbitrary redirect, no injection | **PARTIAL — 2 blockers** | GET/HTTPS/JSON/cache/no-credentials pass (`download-manifest.js:20-37,64-78`). Size cap and redirects fail: SEC-F-01, SEC-F-04. |
| 2 | Download integrity: availability semantics, checksum/size verification, HTTPS + first-party URL, no fake verified flags, no unsigned-as-trusted claims | **PARTIAL — 2 blockers** | CI download-back + SHA-256/size checks pass (`publish.py:202-228`, `verify.py:104-133`); fallback manifest all-false (`site/download.json:10-108`); generated flags gated (`common.py:276-349`). First-party URL and OS-status disclosure fail: SEC-F-02, SEC-F-05. |
| 3 | Signing: Ed25519 release signing separate from OS code signing; OS status truthful | **PARTIAL** | Fail-closed gate `publish.py:76-77,122-131`, `signing.py:133-206`; Ed25519 only (`signing.py:14-18`); OS unsigned stated in `common.py:33-46` and `signing-readiness.yml:18-38`. Public page disclosure missing: SEC-F-05. |
| 4 | Service worker: app shell only, no installer/manifest caching, no secrets | **PASS** | `sw.js:12-42` (`SHELL`, `CACHEABLE`, `NEVER_CACHE` with `/api/`, `/download.json` and installer extensions), `sw.js:65-99` (only `isCacheable` writes). |
| 5 | Electron: no public mirror by default, no remote code, isolation/preload, no desktop capability in browser mirror | **PASS** | `desktop-app/main.js:250-278` (`contextIsolation`, `sandbox`, `nodeIntegration:false`, `preload:undefined`, loopback-only loadURL + token, deny non-HTTP(S)); `uiRoot()` uses local bundled `resources/site` only (`:68-82`); no `ipcRenderer`/`contextBridge` in `site/ui/*.js`. |
| 6 | Installer privileges: no shell installers, no SmartScreen/Gatekeeper bypass, user data preserved, no manifest execution | **PASS** | `package.json:61-76` (`oneClick:false`, `perMachine:false`, `deleteAppDataOnUninstall:false`), `build/nsis-keel.nsh:9-19`, `.github/workflows/lifecycle.yml:66-81`; `main.js:199-220` uses `spawn` with an args array (no shell) and writes advisory state only. |
| 7 | Supply chain: pinned dependencies, no CI secret exposure, least privilege | **PASS** | SHA-pinned actions in all workflows; `npm ci` + offline + electron-builder pin check (`build-desktop.yml:87-105`); `--require-hashes` Python lock; gitleaks SHA-256 verify and redaction (`secret-scan.yml:22-49`); default `contents: read`, write only in `publish` (`build-desktop.yml:37-38,322-323`); signing keys staged in `RUNNER_TEMP` outside artifacts (`build-desktop.yml:72-86,140-153,210-223`); readiness reports CONFIGURED/MISSING only. |
| 8 | Automated deterministic tests | **PASS** | 41 passed; 7 known gaps are `xfail(strict=False)` with file:line evidence and become XPASS on remediation. |

## Findings ranked by severity

### SEC-F-01 — HIGH — manifest proxy follows unvalidated redirects

`keel/site/api/download-manifest.js:41-46` sets `redirect: "follow"`; the
HTTPS check at `:35-37` applies only to the *configured* URL, never to any hop
that follows. A first-party endpoint that redirects (compromised, misconfigured,
or an open redirect) can make the proxy fetch and re-serve content from an
arbitrary HTTP(S) origin as if it were the published first-party manifest.

**Remediation:** `redirect: "manual"`, cap hops (≤2), validate every hop for
`https:` and an approved first-party host before following, reject otherwise.
Test: `test_proxy_does_not_follow_unvalidated_redirects` (xfail).

### SEC-F-02 — HIGH — download URLs are HTTPS-only, not first-party/approved

`keel/site/ui/download.js:39-50` `safeUrl()` accepts **any** `https:` origin
(plus loopback HTTP for local dev). The acceptance contract requires a public
URL that is HTTPS **and first-party/approved**. A tampered manifest (enabled by
SEC-F-01) can therefore point the download button at an attacker-controlled
installer; the same tampered manifest supplies the matching `sha256`/`size`, so
the "SHA-256 verified" badge provides no origin binding.

**Remediation:** enforce an allowlist of approved host + path prefixes for both
primary and alternative URLs (e.g. the first-party GitHub Releases download
path or a configured binaries host); reject everything else. Test:
`test_download_page_restricts_urls_to_approved_first_party_hosts` (xfail,
`safeUrl("https://evil.example/Keel-Setup.exe")` currently returns a URL).

### SEC-F-03 — MEDIUM — release-manifest `files` URLs never positively require HTTPS

`keel/src/keel/release/verify.py:219-221` rejects `http://` but does not require
`https://` (contrast the correct channel check at `:115-120`). `file://`,
`ftp://`, and other schemes reach `urllib.request.urlopen` at `:32`. A signed
or user-supplied release manifest can make the verifier read local files or
fetch non-HTTPS resources.

**Remediation:** require `url.startswith("https://")` for every `files` entry,
with the explicit loopback exception only when `allow_http=True`. Test:
`test_release_manifest_files_require_https_scheme` (xfail).

### SEC-F-04 — MEDIUM — proxy size cap counted in UTF-16 code units, not bytes

`keel/site/api/download-manifest.js:60` uses `text.length > MAX_BYTES` for a
256 KB cap after the entire body is buffered. Multibyte JSON can be 2–4× the
intended byte limit and still be served. Test: a 200,000-character `é` JSON
payload (≈400 KB UTF-8) currently returns HTTP 200.

**Remediation:** stream the body with a byte counter and abort past `MAX_BYTES`;
check `Content-Length` before reading; at minimum compare
`Buffer.byteLength(text, "utf8")`. Test: `test_proxy_size_cap_is_enforced_in_bytes`
(xfail).

### SEC-F-05 — MEDIUM — public download page no longer discloses unsigned OS signing

The rewritten `site/ui/download.js` no longer renders `channel.notes`, and
`site/download.html` has no hosting note. The honest disclosure from
`common.py:33-46` ("Unsigned — expect SmartScreen" / "Gatekeeper will block")
is therefore absent from the public surface, while the UI repeatedly says
"verified installer" and "SHA-256 verified". Ed25519 release signatures are
**not** OS code signatures; presenting the page without that distinction is an
unsigned-as-trusted presentation risk.

**Remediation:** restore a permanent disclosure that installers are unsigned
and that Ed25519 manifest signatures verify file integrity, not OS trust;
render `channel.notes` again or add a static hosting note. Test:
`test_download_page_discloses_unsigned_os_signing_status` (xfail).

### SEC-F-06 — LOW — update check accepts an unsigned manifest when no key is configured

`keel/desktop-app/main.js:186-196` passes `--public-key` only if
`KEEL_UPDATE_PUBLIC_KEY_PATH` is set, and `updater.py:61-70` verifies the
manifest signature only when a key object is present. With
`KEEL_UPDATE_MANIFEST_URL` set and no key, an unsigned manifest can produce an
advisory plan. Impact is limited: `update-state.json` is written but never read
by any runtime code and no artifact is auto-downloaded or installed.

**Remediation:** require a public key whenever an update manifest is configured,
or label the stored plan `signatureVerified:false`. Test:
`test_update_check_requires_a_public_key_when_manifest_is_configured` (xfail).

### SEC-F-07 — MEDIUM — verification downloads follow redirects without re-validation

`keel/src/keel/release/verify.py:31-32` relies on urllib's default redirect
following; `load_manifest` at `:250` does the same. Only the original URL is
scheme-checked (`fetch_bytes:27`, `verify_manifest:115-120`,
`verify_release_manifest:219-221`). An approved HTTPS asset URL can redirect to
`http://` or `file://` and the bytes are still treated as verified against the
manifest checksum.

**Remediation:** install a redirect handler that validates every hop as HTTPS
(or loopback HTTP only with `allow_http=True`) before allowing it. Test:
`test_artifact_download_validates_redirect_targets` (xfail).

## XFAIL gap register

| Test | Finding |
|---|---|
| `test_proxy_does_not_follow_unvalidated_redirects` | SEC-F-01 |
| `test_download_page_restricts_urls_to_approved_first_party_hosts` | SEC-F-02 |
| `test_release_manifest_files_require_https_scheme` | SEC-F-03 |
| `test_proxy_size_cap_is_enforced_in_bytes` | SEC-F-04 |
| `test_download_page_discloses_unsigned_os_signing_status` | SEC-F-05 |
| `test_update_check_requires_a_public_key_when_manifest_is_configured` | SEC-F-06 |
| `test_artifact_download_validates_redirect_targets` | SEC-F-07 |

All are `xfail(strict=False)`: the suite stays green, each defect remains
visible, and each flips to XPASS when the control is actually added. No control
was relaxed to obtain a pass.

## Final security acceptance

**BLOCKED for production distribution.** Two High findings (SEC-F-01,
SEC-F-02) and four Medium findings (SEC-F-03, SEC-F-04, SEC-F-05, SEC-F-07)
must be remediated before the manifest proxy is enabled or the first public
release is published; SEC-F-06 is an accepted low-risk follow-up.

Current exposure is contained: `KEEL_DOWNLOAD_MANIFEST_URL` is not configured,
so the proxy returns 503 (`download-manifest.js:26-28`) and the fallback
manifest advertises no available installer. Do not set that variable and do not
advertise availability until SEC-F-01/02 are fixed and their xfail tests XPASS.

Everything else reviewed — fail-closed Ed25519 release gating, separation from
OS signing, Electron renderer isolation and loopback-only loading, installer
privileges and user-data preservation, service-worker caching boundaries, CI
least privilege, SHA-pinned actions and dependencies, and no secret exposure —
is accepted as-is.
