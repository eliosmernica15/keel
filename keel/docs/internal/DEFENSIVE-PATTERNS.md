# Defensive-patterns reading list — D6.23

Owner: Agent H. Audited 2026-11-24.

Read this file **before** touching any of the surfaces below. It is Keel's own
derived checklist, written from the invariants already enforced in this
repository and from defects found in this round. It is not a copy of the
upstream DS `docs/defensive-patterns/*` pages; where those are cited in the
plan they remain external reading, not vendored text.

| Trigger | Read first | Rule enforced in this tree |
|---|---|---|
| Package surface / public API | `keel/AGENTS.md`, `architecture.md`, `keel/src/keel/d6_reliability_backend.py` | D6.1 upgrade guide on breaking change; D6.11 typed `KeelError` with code; D6.12 public exports have docstrings; D6.10 source plane vs artifact plane stays separate. |
| Remote services / providers | `keel/src/keel/provider_validation.py`, `keel/docs/UI-BACKEND-CONTRACT.md`, `THIRD_PARTY_NOTICES.md` | D6.8 validate at boundaries; redact credentials before remote calls (AGENTS.md); no fabricated provider/model/audit rows (QA read-through in `UI-DEFECT-LOG.md`); test-fire integrations after credential save. |
| Client state / UI | `keel/docs/UI-DESIGN-SYSTEM.md`, `keel/docs/UI-ARCHITECTURE.md`, `keel/docs/UI-DEFECT-LOG.md` §6 | E2.1 presenters are pure; D4.8 copy comes from locale/typed dictionaries; QA-F-003/004: do not claim a live bridge that was not verified; QA-F-013: keyboard handlers must survive focus changes. |
| Conversation / session behaviour | `keel/src/keel/session.py`, `keel/docs/EVENTS.md`, `keel/docs/UI-BACKEND-CONTRACT.md` | D2.11 model-visible ⇔ logged; D2.12 projection seam; D2.13 versioned, never-overwritten generations; do not trust a client-side optimistic row as a durable fact. |
| Lifecycle / concurrency / subprocess / teardown | `keel/src/keel/invariant_contracts.py`, `keel/src/keel/release/`, `keel/docs/UI-DESKTOP-RENDERING.md` | E4.8 every test owns and tears down its resources; V1 scope disposal is reversible; all destructive operations use recoverable trash / approval / dry-run (AGENTS.md); fail closed when state is unknown (D6.11). |

## Standing checks before editing any of those surfaces

1. **Boundary, not interior**: validate untrusted input where it enters; do not
   add hostile-input tests for values the typed interface already guarantees
   (D6.8).
2. **Explicit defaults**: resolve request → spec explicitly; no hidden
   `or default` inside a runner (D6.4).
3. **Typed failures**: expected failures are coded values/errors; unexpected
   ones stop dependent work and are visibly reported. Empty `except` blocks are
   not acceptable (D6.11).
4. **No invented state**: if the bridge, provider, hierarchy or cost data is
   unavailable, say so. This round's Fleet/Cost/Duet panels were explicitly
   tested for honest unavailable states (`UI-E2E-GUIDE.md`, §new-requirement coverage).
5. **Test the world**: re-read the file/re-run the command externally; assert
   untouched files are byte-identical (E4.11). Change obsolete tests with the
   behaviour they describe (D6.14).
6. **Relevant checks only**: see `keel/docs/internal/BUILDER-PROCESS.md` D6.20.

## Evidence boundary

This is a reading discipline. Recording that a human or agent read it is not
itself proof of safe code, so no "read" flag or fake success check is emitted.
The companion evidence is the defect fixes in `keel/docs/UI-DEFECT-LOG.md` §6
and the contract tests under `keel/tests/`.
