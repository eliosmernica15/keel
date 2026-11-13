# Skills provenance (2026-11-12)

See `resources/default-skills/PROVENANCE.md` for the authoritative record and
`../licensing-and-provenance-review.md` (Addendum 2026-11-12) for the
project-level provenance entry.

Summary: Keel ships **21 default skills** — 18 vendored verbatim from
`github.com/anthropics/skills` @ `2c5958ecac7cee2b583967a2c4981d0f4a75c579`
(Apache-2.0, notices preserved, `doc-coauthoring` excluded for lack of a
licence), and 3 authored from scratch for this project (`windows-debugging`,
`keel-meta`, `python-codebase`).

Users can extend at `~/.keel/skills/<name>/` (user scope) and
`.keel/skills/<name>/` (project scope; treated as untrusted data — bodies are
never executed, injection-shaped lines are flagged, an untrusted banner is
prepended on render).
