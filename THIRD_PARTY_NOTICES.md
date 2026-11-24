# Keel — Third-Party Notices

**Audit date:** 2026-11-24. **Scope:** the manifests and installed dependency
metadata in this worktree (`keel/pyproject.toml`,
`keel/fleet-next/package.json`, `keel/desktop-app/package.json`, the two
`package-lock.json` files, and the installed `node_modules` / Python
distribution metadata). The complete machine-generated package table is in
`keel/docs/DEPENDENCY-LICENSE-INVENTORY.md`; this file is the human-readable
summary. No notice below was invented: every SPDX expression is copied from a
manifest, an installed `package.json` `license` field, or the component's own
license file.

## 1. Licensing status and governance note

- **No MIT grant was added to Keel code.** `DECISIONS.md` D-037 rejected the
  MIT portion of W1.18 because Keel v5 §0.2 requires proprietary,
  all-rights-reserved code; the recorded resolution is
  "THIRD_PARTY_NOTICES only, Keel proprietary". A draft MIT `LICENSE` was
  created during this round and removed on lead review to honour that owner
  decision. Keel's manifests remain authoritative: `keel/pyproject.toml`
  (`license = { text = "Proprietary" }`), `keel/desktop-app/package.json`
  (`"license": "Proprietary"`) and `keel/desktop-app/build/LICENSE.txt`
  ("proprietary software"). W1.18 is therefore recorded as partially
  owner-gated: the THIRD_PARTY_NOTICES portion is implemented; the MIT portion
  is rejected by D-037. No repo visibility, security settings or generated
  registry was changed.
- Third-party components keep their own licenses. Nothing in this file grants
  rights over a third-party component beyond the license that component ships.

## 2. Declared dependencies observed this round

### Python (`keel/pyproject.toml`)

| Component | Declared constraint | Version observed here | License (observed) | Evidence |
|---|---|---|---|---|
| tzdata | `>=2024.1` (runtime) | 2026.5 | Apache-2.0 | installed distribution `License-Expression` |
| cryptography | `>=42.0` (runtime; AES-256-GCM secret encryption) | 50.0.1 | Apache-2.0 OR BSD-3-Clause | installed distribution `License-Expression` |
| Pillow | `>=10.0` (runtime; image handling) | 11.1.0 | MIT-CMU | installed distribution metadata (`License` + classifier) |
| keyring | `>=24.0` (runtime; OS keychain) | not installed on this host | MIT | earlier installed-metadata audit recorded in `keel/docs/proprietary/THIRD_PARTY_NOTICES.draft.md`; **not re-verified this round** |
| setuptools | `>=68` (build backend) | 84.0.0 | MIT | installed distribution `License-Expression` |

Additional installed distributions relevant to packaging/testing, not all
declared directly in `pyproject.toml`: certifi 2026.7.22 (MPL-2.0), PyInstaller
6.19.0 (GPLv2-or-later with bundling exception; build-only), pytest 9.0.2
(MIT; test-only).

### Node — `keel/fleet-next` (local web UI)

| Component | Declared constraint | Version observed here | License (observed) | Evidence |
|---|---|---|---|---|
| next | `^15.1.6` (runtime) | 15.5.29 | MIT | installed `package.json`, plus `node_modules/next/license.md` (© 2025 Vercel, Inc.) |
| react | `^19.0.0` (runtime) | 19.3.1 | MIT | installed `package.json` and `LICENSE` (© Meta Platforms, Inc. and affiliates) |
| react-dom | `^19.0.0` (runtime) | 19.3.1 | MIT | installed `package.json` and `LICENSE` |
| **@playwright/test** | `^1.65.1` (**devDependency**, real-browser E2E/a11y) | **1.65.1** | **Apache-2.0** | installed `package.json` (`license`, `author: Microsoft Corporation`, `repository: microsoft/playwright`), `LICENSE` (Apache-2.0 text) and `NOTICE` ("Playwright — Copyright (c) Microsoft Corporation"; derived from Puppeteer, Apache-2.0) |
| typescript | `^5.7.3` (dev) | 5.9.3 | Apache-2.0 | installed `package.json` and `LICENSE.txt` |
| @types/node | `^22.10.5` (dev) | 22.20.5 | MIT | installed `package.json` |
| @types/react | `^19.0.8` (dev) | 19.3.0 | MIT | installed `package.json` |
| @types/react-dom | `^19.0.3` (dev) | 19.3.0 | MIT | installed `package.json` |

Playwright's `NOTICE` text is preserved here verbatim:

> Playwright
> Copyright (c) Microsoft Corporation
>
> This software contains code derived from the Puppeteer project
> (https://github.com/puppeteer/puppeteer), available under the Apache 2.0
> license (https://github.com/puppeteer/puppeteer/blob/master/LICENSE).

### Node — `keel/desktop-app` (Electron shell)

| Component | Declared constraint | Version observed here | License (observed) | Evidence |
|---|---|---|---|---|
| electron | `^42.0.0` (dev/build) | 42.11.18 | MIT | installed `package.json` |
| electron-builder | `^26.0.0` (dev/build) | 26.18.0 | MIT | installed `package.json` |

The packaged Electron app also carries Chromium/V8 license text
(`LICENSES.chromium.html` in the packaged app, recorded in
`keel/docs/proprietary/THIRD_PARTY_NOTICES.draft.md`). It is not in the npm
lockfile and is therefore not enumerated here.

### Transitive npm packages

Both lockfiles are lockfileVersion 3 and have **no `license` field on any
`packages` entry**, so the license families below come from the installed
`package.json` files, not from the lockfiles. Full per-package rows are in
`keel/docs/DEPENDENCY-LICENSE-INVENTORY.md`.

| Tree | Packages | License families (counts) |
|---|---:|---|
| fleet-next | 31 | MIT 17; Apache-2.0 7; ISC 2; BSD-3-Clause 1; 0BSD 1; CC-BY-4.0 1; Apache-2.0 AND LGPL-3.0-or-later AND MIT 1; Apache-2.0 AND LGPL-3.0-or-later 1 |
| keel-desktop | 240 | MIT 183; ISC 24; BSD-3-Clause 9; BlueOak-1.0.0 7; Apache-2.0 6; BSD-2-Clause 5; Python-2.0 1; WTFPL 1; WTFPL OR ISC 1; 0BSD 1; (MIT OR CC0-1.0) 1; (WTFPL OR MIT) 1 |

The fleet-next tree is used for local development and browser verification;
the draft release notice (`keel/docs/proprietary/THIRD_PARTY_NOTICES.draft.md`)
records that those dependencies are not copied into the desktop installer. If
that changes, this table must be re-audited before release. The desktop-app
tree is a build/dev toolchain, not a shipped runtime dependency set, except
for Electron's bundled runtime as noted above.

## 3. Upstream notices preserved from earlier audits

These entries are carried forward from the existing
`keel/docs/THIRD_PARTY_NOTICES.md` and the repository's own license files. They
are not new claims.

- **OpenCode** (https://github.com/anomalyco/opencode, MIT, © 2025 opencode).
  No OpenCode source has been copied into Keel; the MIT permission and warranty
  text is preserved in `keel/docs/THIRD_PARTY_NOTICES.md`.
- **OpenAI Codex CLI** (https://github.com/openai/codex, Apache-2.0).
  `src/keel/exec_policy.py` is documented there as a clean-room reimplementation
  of decision semantics, with upstream attribution preserved under Apache-2.0 §4.
- **Work Sans font** (SIL OFL 1.1, © 2019 The Work Sans Project Authors).
  Font files under `site/ui/fonts/` and `desktop/ui/fonts/`; license text at
  `resources/fonts/WorkSans-OFL.txt`.
- **models.dev catalog data** (MIT, © 2025 models.dev). Source URL and
  attribution at `keel/resources/catalog/LICENSE.models-dev.txt` and in
  `keel/resources/catalog/providers.json`.
- **Bundled skills** (18 directories under `keel/resources/default-skills/`,
  Apache-2.0 license files, e.g. `pdf/LICENSE.txt`, `skill-creator/LICENSE.txt`,
  `docx/LICENSE.txt`). Any additional upstream notices are tracked in
  `keel/resources/default-skills/UPSTREAM_THIRD_PARTY_NOTICES.md` where present.
- **Keel-owned assets** (branding, icons, installer artwork and copy) remain
  Keel-owned; see `keel/desktop-app/build/LICENSE.txt`.

## 4. Limitations

- This is a repository-level notice audit, not a legal opinion.
- Version numbers are the versions installed in this worktree;
  `pyproject.toml` and the npm manifests use ranges, not exact pins, so a fresh
  install may resolve to different versions. Re-run the inventory generator
  before a release notice is published.
- `keyring` and Chromium's bundled license set could not be re-verified from
  local metadata in this round and are explicitly marked as carried-forward.
- No generated feature registry (`PLAN-INDEX.json`, `parity.json`) was edited.
