# FINAL RELEASE ARTIFACTS — what actually exists at `35fb2b8`

> Documentation-only inventory at completion HEAD
> `35fb2b8abfd784393b2b252e2b9e2927aba817dd` (tree identical to
> `c512f87971a02b05d9a9422338522f66495c0eeb`). No artifact was built, signed,
> tagged, pushed or published by this reconciliation. No distribution link is
> asserted: none exists in tracked metadata. Checksums below are reproduced only
> where a real value was recorded, with its exact provenance and limitations.

## 1. Version and tracked release metadata

| Item | Exact tracked value / verification |
| --- | --- |
| Version constant | `0.1.1` in `keel/src/keel/__init__.py` and `keel/pyproject.toml`; `python keel/scripts/check_version_sync.py` at `C0` → `OK - all sources agree on version 0.1.1 (tag v0.1.1)` (7 sources) |
| Public download manifest | `keel/site/download.json` — tracked, `version: "0.1.1"`, `tag: "v0.1.1"`, `generated: "fallback"`, `published_at: null`, `verified_at: null`, `base_url: null`, `release_manifest_url: null` |
| Release code (tracked) | `keel/src/keel/release/{artifacts,build,cli,common,github,licenses,packaging,publish,signing,updater,verify}.py`, `release_feed.py`, `release_gaps.py`, `release_integrity.py` |
| Release CI / readiness (tracked) | `.github/workflows/build-desktop.yml`, `.github/workflows/verify-install.yml`, `.github/workflows/signing-readiness.yml` |
| Signing documentation (tracked) | `keel/docs/release/SIGNING-PREPARATION.md`, `keel/docs/FINAL-RELEASE-OPERATIONS.md`, `master-plan-v6-signing-evidence.md` |
| Plan registry (tracked) | `PLAN-INDEX.json` = `parity.json`, SHA-256 `62fd5c6ac2d166e8cb1f5752c168d22d56d767c7e6a5bf9384696756a4a5b2f6`, recomputed at `C0`; 865 rows (854 verified / 9 not_started / 2 blocked). This is a planning registry, **not** a release artifact. |

`keel/site/download.json` channel state (all channels, no exceptions):

| Channel | Declared filename | `sha256` | `url` | `available` | `verified` | Note |
| --- | --- | --- | --- | --- | --- | --- |
| Windows x64 | `Keel-Setup-0.1.1.exe` | `null` | `null` | `false` | `false` | "Not publicly hosted yet; there is nothing to download." |
| macOS arm64 (PKG) | `Keel-0.1.1-macos-arm64.pkg` | `null` | `null` | `false` | `false` | same; Intel `Keel-0.1.1-macos-x64.pkg` alternative also `null`/`false` |
| Linux x86_64 (DEB) | `Keel-0.1.1-linux-amd64.deb` | `null` | `null` | `false` | `false` | same; `Keel-0.1.1-linux-x86_64.rpm` alternative also `null`/`false` |

**No distribution links exist.** Source-repository references in historical reports are
not download endpoints and are not reproduced here as release links.

## 2. Artifacts that do **not** exist at the completion HEAD

Verified by `git ls-files` over the tracked tree and by an on-disk file scan:

| Expected release artifact | Status |
| --- | --- |
| `RELEASE-MANIFEST.json` | Absent — not tracked, not on disk |
| `RELEASE-SHA256SUMS.txt` | Absent — not tracked, not on disk |
| `keel/dist/` installers (exe/pkg/deb/rpm) | Absent — gitignored generated output; no installer in the tree |
| `*.sig` detached signatures | Absent — 0 files |
| Signed release tag / GitHub Release | None created by this workstream |
| `download.json` public manifest URL | `null` — no hosted manifest |

Consequently there is **no published artifact checksum** to report. The six artifact-
dependent tests that failed in earlier clean checkouts did so because these generated,
owner-gated files were absent; the definitive final-tree suite (`4610 passed / 0 failed
/ 54 skipped`) includes deterministic test-only release fixtures and does not claim the
real artifacts exist.

## 3. Real checksums that do exist (and their exact limits)

These values are genuine, locally measured hashes recorded in the evidence docs. They
are **not** release checksums: they are untracked local builds, unsigned, produced
before the completion HEAD, and not published. They are listed for completeness, not
as download verification data.

| Value | Object | Size | Provenance | Limit |
| --- | --- | --- | --- | --- |
| `9E8B67307E850CF7D32BC4EE8AA7714119A8B33F86E08F02336BAF0A968A09F2` | `dist/keel-sidecar/keel.exe` (before rebuild) | 31,160,346 B | `keel/docs/UI-DESKTOP-PACKAGING.md` §8.2 | Pre-reconciliation sidecar; superseded |
| `B091538D9E2E1284DAD3F85AC0B31DC532073331D140777B2FFA282EBD8431FF` | rebuilt sidecar / `build/resources/keel/keel.exe` | 31,436,836 B | same §8.2, rebuilt after merge `c80c2e1…` | Local, untracked, unsigned, pre-`C0` |
| `F6CAE185A6A2AA53D61572E4C9930B3750CE418FC9AAF38BD788CCC6E63743BB` | locally built `dist/Keel-Setup-0.1.1.exe` | 143,931,562 B | same §8.3, `npm run build:win` 2026-11-25 | Build log states "no code signing certificate configured, signing is skipped"; local, untracked, pre-`C0` |
| `e6f53616a28b1270145e4ce797b271dbe873a2200ed4b613ba8a2a5efe760101` | UI `index.html` body in a local HTTP probe | 47,816 B | same §8.1/§8.3 | Probe response body, not a shipped installer |
| `62fd5c6ac2d166e8cb1f5752c168d22d56d767c7e6a5bf9384696756a4a5b2f6` | `PLAN-INDEX.json` = `parity.json` | — | recomputed at `C0` | Tracked plan registry, not a release artifact |

No `RELEASE-MANIFEST.json` signature, no `RELEASE-SHA256SUMS.txt` entry and no
`.sig` file exists for any of the above. Do not present them as verification of a
published release.

## 4. Signature status — honest

| Aspect | Status at `C0` |
| --- | --- |
| Ed25519 hard-fail gate | **Implemented**: `SigningGateError`, `require_signed_enabled()`, `verify_signed_release()` in `keel/src/keel/release/signing.py`; real `publish` is always gated; `build-desktop.yml` has a `verify-release-signatures` job; 10 signing-gate tests and 36 combined tests green (`master-plan-v6-signing-evidence.md`, `C9`) |
| Keys configured | **None.** `KEEL_RELEASE_SIGNING_KEY` and `KEEL_RELEASE_SIGNING_PUBLIC_KEY` absent; `signing-readiness.yml` reports only `=CONFIGURED` / `=MISSING` and observed `total_count=0` in the prior round |
| Signed manifest / `.sig` assets | 0 |
| OS code signing / notarization | Not wired into CI; electron-builder reports "no code signing certificate configured, signing is skipped"; no Authenticode/Developer ID/notarization secrets |
| Behaviour when a tag is pushed today | Real publish fails closed (`RELEASE SIGNING GATE FAILED`, non-zero) — this is intended; nothing is published as signed or verified |
| Final classification | PR-20 `OWNER_ACTION_REQUIRED`; see `FINAL-OWNER-ACTIONS.md` A2 |

No artifact in this tree may be described as signed, verified, trusted or published.

## 5. Deployment status

- Deployed instances: **0**.
- Published releases / pushed tags by this workstream: **0**.
- `keel/site/download.json`: all channels `available: false`, `verified: false`, `url: null`.
- Signed clean-VM upgrade/rollback (PR-17): not run.
- `PASS_VERIFIED` gates in `FINAL-PRODUCTION-READINESS-MATRIX.md`: **0**.

Any future change to these fields must be the result of the owner actions in
`FINAL-OWNER-ACTIONS.md` (A2 signing identity, A4 governance, A5 deployment
authorization), performed at the exact SHA that is actually promoted.
