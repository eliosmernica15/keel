# Bundled default skills — provenance

**Source:** https://github.com/anthropics/skills
**Commit:** `2c5958ecac7cee2b583967a2c4981d0f4a75c579` (2026-11-06, shallow clone)
**Licence:** Apache License 2.0 — each vendored skill carries its own `LICENSE.txt`.
**Vendored by:** Keel project (this directory) — 2026-11-12.

## Policy

- These are **Anthropic's openly published Agent Skills**, vendored verbatim. They are
  their authors' work under Apache-2.0, not ours. Keel does not claim authorship and
  does not rewrite their prose. Apache-2.0 requires preservation of copyright/licence
  notices — do not delete `LICENSE.txt` files.
- **`doc-coauthoring` is deliberately excluded** — it carries no licence file, and
  absent an explicit licence we do not redistribute it.
- The upstream `THIRD_PARTY_NOTICES.md` is kept at
  `default-skills/UPSTREAM_THIRD_PARTY_NOTICES.md`.
- Users may install their own skills at `~/.keel/skills/<name>/` or project-local
  `.keel/skills/<name>/`; project-scope skills are treated as untrusted data.
- No skill is executed by the loader. Any shell-injection-shaped line in a body is
  flagged, never run.
- If the upstream repo revs, update this manifest and the recorded commit hash; do
  not hand-edit vendored bodies.

## Vendored set

academy-guide, algorithmic-art, brand-guidelines, canvas-design, claude-api,
discernment-nudge, docx, frontend-design, internal-comms, mcp-builder, pdf, pptx,
skill-creator, slack-gif-creator, theme-factory, web-artifacts-builder,
webapp-testing, xlsx (18 skills).
