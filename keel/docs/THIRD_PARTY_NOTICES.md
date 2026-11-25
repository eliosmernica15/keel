# Keel — Third-Party Notices

> **Current audit (2026-11-24):** the repository-root `THIRD_PARTY_NOTICES.md`
> is the current dependency audit, and `keel/docs/DEPENDENCY-LICENSE-INVENTORY.md`
> is its generated per-package table. `DECISIONS.md` D-037 rejects applying MIT
> to Keel code; a draft MIT `LICENSE` created this round was removed on lead
> review. The proprietary manifests remain authoritative, and the owner-gated
> W1.18 MIT portion is recorded in `keel/docs/MASTER-PLAN-INVENTORY.md` §6.1.
> The text below is the historical notice, preserved rather than rewritten.
> A further dependency re-audit was recorded on 2026-11-25 in the root notice
> (§5): declared dependency sets and installed versions were re-sampled, no new
> dependency or license grant was added, and Keel code remains proprietary.

Historical statement from this notice: Keel's licensing was recorded here as
proprietary, with a pointer to a `LICENSE` file that was not present in the tree
at the time. Do not read this line as a current license grant; see the note
above and the root notice.

Where upstream code, assets, or documentation are reused **unchanged**, their
original notices are preserved below. Where Keel rewrites or re-implements
upstream functionality in new Keel code (Apache-style clean-room where noted),
no upstream copyright is claimed.

## 1. OpenCode (MIT)

- Repository: https://github.com/anomalyco/opencode (`dev` branch as of 2026-11-18)
- License: MIT
- Copyright: (c) 2025 opencode

> Permission is hereby granted, free of charge, to any person obtaining a copy
> of this software and associated documentation files (the “Software”), to deal
> in the Software without restriction, including without limitation the rights
> to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
> copies of the Software, and to permit persons to whom the Software is
> furnished to do so, subject to the following conditions: The above copyright
> notice and this permission notice shall be included in all copies or
> substantial portions of the Software. THE SOFTWARE IS PROVIDED “AS IS”,
> WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT
> LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR
> PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT
> HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN
> ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
> CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

## 1a. OpenAI Codex CLI (Apache-2.0) — exec policy semantics

- Repository: https://github.com/openai/codex
- Inspected commit: `ef33e43a159beeeb95dddf7cde05926cc9871929` (`main`)
- License: Apache License 2.0 (full text in the upstream `LICENSE`)
- Source inspected: `codex-rs/execpolicy/src/{decision,rule,policy,parser}.rs`,
  `examples/example.codexpolicy`, `tests/basic.rs`

Keel's `src/keel/exec_policy.py` is a **clean-room Python reimplementation of
the documented decision semantics** of that engine. No upstream source file was
copied; the upstream syntax (Starlark) and runtime (Rust) are not used. The
concepts — severity-ordered decisions, first-token prefix rules with
alternatives, network domain compilation and load-time self-tests — are
documented in the upstream README and implemented independently in Python.

Licensed under the Apache License, Version 2.0 (the "License"); you may not use
that implementation except in compliance with the License. You may obtain a
copy at http://www.apache.org/licenses/LICENSE-2.0. Keel's adaptation is
provided under Keel's proprietary license; this notice preserves the upstream
attribution required by Apache-2.0 §4.

Full source-repository register: `docs/research/source-repository-register.md`.

Usage as of this milestone: **audit only. No OpenCode source has been copied into Keel yet.**
Any future reuse will be recorded here with the upstream copyright notice attached.

## 1b. Work Sans font (SIL OFL 1.1) — optional high-legibility option

- Source shipped in repo: `site/ui/fonts/WorkSans-Regular.ttf` and
  `desktop/ui/fonts/WorkSans-Regular.ttf`
- License text: `resources/fonts/WorkSans-OFL.txt` (not shipped in the public
  website tree, which forbids GitHub links); Copyright 2019 The Work
  Sans Project Authors, https://github.com/weiweihuanghuang/Work-Sans)
- Use: optional B4.9 accessibility setting. Not a clinical dyslexia font; the
  UI describes it as a high-legibility OFL font. No other font was downloaded.

## 1c. Pillow (PIL) — image handling for screenshot gallery and visual diff

- Declared dependency: `Pillow>=10.0` in `pyproject.toml`
- License: HPND-style permissive (Pillow Software License / MIT-CMU)
- Use: B5.6 screenshot gallery metadata and C4.11 pixel-level UI diff.
  OpenCV and NumPy are deliberately **not** dependencies; optional QR rendering
  uses a runtime-only import and degrades gracefully.

## 2. Permissive runtime dependencies used by Keel (non-exhaustive)

These are consumed as libraries, not copied source.

- Electron — https://github.com/electron/electron (MIT)
- PyInstaller — https://github.com/pyinstaller/pyinstaller (MIT)
- Inno Setup — https://jrsoftware.org/isinfo.php (proprietary, installer tool only; not redistributed in Keel source)

## 3. Keel-owned assets

- Keel branding, icons, sidebar/header BMPs, splash screen, wordmark and copy: proprietary, owned by Keel Team.

## 4. Upstream assets in this repository

None beyond the OpenCode notices above. If this changes, entries will be added here before code/assets are committed.
