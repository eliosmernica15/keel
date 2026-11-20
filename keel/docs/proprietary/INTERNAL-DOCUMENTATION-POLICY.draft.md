# DRAFT — Internal documentation policy

**Status: DRAFT. Internal only. Not published.**

The following stay in the private development repository and must not appear on
the public website, in installers, or in SDK/extension documentation:

- Root planning documents and `keel/docs/` engineering records.
- `agent-reference-shots/`, `claude-code-evidence.md`, `agent-evidence*.md`,
  `prompt-pattern-analysis.md` and other third-party captures/analysis.
- `.verify-*`, `.build/`, scratch scripts and debug logs.
- Build metadata such as `.vercel/` and `builder-debug.yml`.
- Internal release/HOSTING notes and private CI references.

Public documentation is limited to product information, installation, user
guides, release notes and verified download metadata. Extension/SDK
documentation remains private by default (v5 G7).

The artifact allowlist in `src/keel/release/artifacts.py` enforces the packaging
side of this policy.
