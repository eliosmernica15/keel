# DRAFT — Third-Party Notices

**Status: DRAFT. Not published. Must be reviewed before the first binary release.**

Keel's original work is proprietary. This draft catalogues third-party material
that must keep its own license notices inside any proprietary binary.

## Shipped runtime components

| Component | Version | License | Notice source |
|---|---|---|---|
| Electron | 42.11.18 | MIT | `LICENSE.electron.txt` in packaged app |
| Chromium/V8 | bundled with Electron | multi-license | `LICENSES.chromium.html` in packaged app |
| tzdata | installed metadata | Apache-2.0 | `tzdata-*.dist-info/licenses/LICENSE` — **license text not yet embedded in sidecar** |
| certifi | installed metadata | MPL-2.0 | `certifi-*.dist-info/licenses/LICENSE` — **not yet embedded in sidecar** |
| Vendored skills (18) | pinned commit | Apache-2.0 | `resources/default-skills/*/LICENSE.txt` and `UPSTREAM_THIRD_PARTY_NOTICES.md` |
| Canvas fonts | pinned | SIL OFL 1.1 | `resources/default-skills/canvas-design/canvas-fonts/*-OFL.txt` |
| models.dev catalog data | 2026-11-20 | MIT, Copyright (c) 2025 models.dev | `resources/catalog/LICENSE.models-dev.txt`, source URL and attribution in `resources/catalog/providers.json` |

## Build-only tools

PyInstaller (GPLv2-or-later with bundling exception), setuptools (MIT),
electron-builder (MIT) and NSIS are build tools and are not shipped as runtime.
Their licenses do not require notices in the distributed binary, but retain
records in the private repository.

## Not shipped

`keel/fleet-next/` dependencies (Next.js, React, sharp, `@vercel/og`, etc.) are
not copied into the desktop installer. If that changes, re-audit their licenses,
including Apache-2.0/MPL-2.0/LGPL-3.0 components.

## Required actions before release

1. Embed or ship tzdata and certifi license texts with the sidecar.
2. Add the vendored-skill and OFL notices to the published notices page.
3. Obtain legal review for GPL-3.0/GPL-2 components referenced in
   `resources/default-skills/UPSTREAM_THIRD_PARTY_NOTICES.md`.
