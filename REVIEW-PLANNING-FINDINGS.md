# Independent review findings — registry reconciliation, priority re-ranking, governance, CI gates

Reviewer: independent read-only subagent (`agent/a4-review-planning`)
Worktree: `C:\Users\Admin\.local\share\opencode\worktree\addenda\review-planning` (branch `agent/a4-review-planning`)
Baseline / reviewed HEAD: `458741e` (`Refresh P0 batch list after 30 features verified`)
Review date: 2026-11-24

Scope reviewed: `PLAN-INDEX.json`, `parity.json`, `Keel_Master_Plan_v6.md`,
`keel/scripts/build_plan_index.py`, `keel/scripts/build_v6_plan.py`,
`keel/docs/plan-sources/` (8 sources + `extracted/*.json`),
`scripts/verify_v6_audit.py`, `scripts/plan_p0_batches.py`,
`keel/scripts/build_dependency_graph.py`, `DECISIONS.md`,
`FREE-TIER-REGISTER.md`, `MODEL-AND-VOICE-LICENSES.json`, `RISKS.md`,
`DEPENDENCY-GRAPH.md`, `REMAINING-WORK-MATRIX.md`,
`.github/workflows/offline-license.yml`, `scripts/check_model_licenses.py`,
`keel/tests/test_offline_runtime.py`, and the `keel/docs/IMPLEMENTATION-PROGRESS.md`
amendment. All temporary analysis scripts were written outside the repo
(`C:\Users\Admin\AppData\Local\Temp\opencode\`) and are not part of this commit.

---

## Verdict summary (per artifact)

| Artifact | Verdict |
| --- | --- |
| `PLAN-INDEX.json` (865 rows) | PASS on structure/counts; FAIL on evidence attribution for 8 `X1.*` rows (H-3) |
| `parity.json` (root, 865 rows) | PASS — byte-identical to `PLAN-INDEX.json`, regenerates identically |
| `Keel_Master_Plan_v6.md` | PASS — regenerates byte-identically |
| Extracted JSONs + 8 source documents | PASS — verbatim at git-blob level; 20-row spot-check clean |
| P0 re-ranking / `original_priority` | PASS — deterministic, rule-faithful, source values preserved |
| `scripts/verify_v6_audit.py` | PASS when run, but weak evidence checks (M-5) and not in CI (H-4) |
| `build_plan_index.py` / `build_v6_plan.py` / `plan_p0_batches.py` | PASS — byte-identical regeneration |
| `keel/scripts/build_dependency_graph.py` | generator code sound, but `DEPENDENCY-GRAPH.md` is STALE (H-1); machine-specific paths (L-9) |
| `DEPENDENCY-GRAPH.md` | **FAIL** — fails its own `--check`; reports 226/637 (H-1) |
| `REMAINING-WORK-MATRIX.md` | **FAIL** — reports 226/637 instead of 268/595 (H-2) |
| `RISKS.md` | **FAIL (partial)** — multiple stale 226/637 risk statements (H-2) |
| `IMPLEMENTATION-PROGRESS.md` amendment | **FAIL (partial)** — "603 not_started"/"being implemented" stale; ledger "final" lines stale (H-2, L-11) |
| `DECISIONS.md` | PASS — 35 decisions, 4 owner-gated, dates sane, no false implementation claims |
| `FREE-TIER-REGISTER.md` | PASS — 43 rows, dates are compilation dates, MUST VERIFY flags honest |
| `MODEL-AND-VOICE-LICENSES.json` | PASS — 11 entries, 0 bundled, no invented license facts, fail-closed policy |
| `.github/workflows/offline-license.yml` | PASS — fails closed on missing `unshare`; license gate proven to reject |
| `scripts/check_model_licenses.py` | PASS — all 6 synthetic cases behaved correctly |
| `keel/tests/test_offline_runtime.py` | PASS (offline logic); repo-wide hash test fails on Windows (M-6) |
| Status reporting 595/268/2 | Registry + final matrix PASS; human-facing docs FAIL (H-2) |

---

## Critical findings

**None.** No artifact was found to fabricate implementations, invent license grants, or
falsify the machine-readable registry. The verified machine-readable state is honest.

## High findings

### H-1 — `DEPENDENCY-GRAPH.md` is stale and fails its own freshness gate
Command:
```
python keel/scripts/build_dependency_graph.py --check
```
Result:
```
STALE: ...\DEPENDENCY-GRAPH.md
EXIT=1
```
Regeneration to a temp file and diff (41 insertions / 51 deletions) shows the committed
report was generated **before** the verification marks:
- header says `verified 226, not_started 637, blocked 2` (SHA-256 `1267a8a7…`), while the
  current registry is `verified 268, not_started 595, blocked 2` (SHA-256 `38120430…`);
- split labels are from the removed `plan-extract/addendum3.json` (`M11a core`, `M17a`,
  `M22a`) rather than the canonical `keel/docs/plan-sources/extracted/addendum3.json`
  (`M11a code-intel core`, `M17a voice`, `M22a packaging`);
- edge count 47 → 46; status-mix cells throughout §3–§6 are outdated.

Additional reproducibility defect: `resolve_plan_path()` hardcodes
`C:\Users\Admin\Desktop\Claude clone\PLAN-INDEX.json` as `CANONICAL_PLAN`, and the default
extract path is `plan-extract/addendum3.json`, which **no longer exists** in the worktree
(it was replaced by `keel/docs/plan-sources/extracted/` in commit `8208fdd`). The generated
report therefore embeds an author-machine-specific absolute path and cannot be reproduced
by running the documented command with no arguments.

### H-2 — Human-facing status documents report stale 226/637 instead of 268/595
`REMAINING-WORK-MATRIX.md` lines 3, 13–14, 20–27, 91 and the entire section 6 are keyed to
the pre-verification registry:
- header SHA-256 `1267a8a7…`;
- "verified 226 / not_started 637 / blocked 2";
- "all 637 Add.3–Add.7 rows are `not_started`" — false: 42 addenda rows (34 tool-contract
  `E*`/`Y*`/`Z*`/`V*` + 8 `X1.*`) are now verified;
- "196 not-started P0" — `plan_p0_batches.py` finds 166;
- section 3 claims "no verified row has a `section`" — false for the 42 addenda rows.

`RISKS.md` repeats the stale figures at lines 26, 47–48, 54, 147, 158, 164 (M0-R1,
M23-R2, M25-R4, M26-R1). `ADDENDA-OPERATION-STATUS.md` lines 15–17, 27, 45 and the
`IMPLEMENTATION-PROGRESS.md` amendment (lines 18–20: "7 features … are being implemented",
"603 `not_started`") are likewise outdated. The machine-readable sources are correct —
`PLAN-INDEX.json`, `master-plan-v6-final-matrix.json` and `.csv` all report
`not_started 595 / verified 268 / blocked 2` with zero status/priority/tier/owner-flag
mismatches — but the documents a human reads to judge honesty contradict them. Neither
`REMAINING-WORK-MATRIX.md` nor `RISKS.md` has a generator, so CI cannot refresh them.

### H-3 — Eight verified `X1.*` features carry misattributed evidence in the canonical registry
`build_plan_index.py::_load_extra_features()` computes correct per-group locals
`src_files`, `test_files`, `evidence` (lines 761–775) but then discards them: lines 790,
793 and 799 unconditionally write `TOOL_CONTRACT_SRC`, `TOOL_CONTRACT_TESTS` and
`TOOL_CONTRACT_EVIDENCE` for **every** verified extra row. Result in `PLAN-INDEX.json`:

- `X1.1`, `X1.2`, `X1.3` → `model_dialects.py` / `test_model_dialects.py` expected;
  registry instead says `tool_contracts.py`, `test_tool_contracts.py`, with evidence text
  "Addendum 7 canonical tool pipeline … 60 passing contract tests".
- `X1.4`, `X1.5` → `edit_formats.py` / `test_edit_formats.py` (wrong in registry).
- `X1.7`, `X1.8` → `repo_map.py` / `test_repo_map.py` (wrong in registry).
- `X1.13` → `steering.py` / `test_steering.py` (wrong in registry).

The underlying implementations and tests **do exist** and pass (see test run below), so no
feature is verified without code/tests; but the registry's evidence pointers are false for
these 8 rows, and `verify_v6_audit.py` only checks field non-emptiness, so it passes. A
reviewer following the registry would inspect the wrong module.

### H-4 — The two freshness/consistency gates are not wired into CI
A scan of all 8 files in `.github/workflows/` found only `check_model_licenses.py` in
`offline-license.yml`. Neither `verify_v6_audit.py` nor
`build_dependency_graph.py --check` (whose own docstring calls it a "CI freshness gate")
is invoked by any workflow. Consequently the stale artifacts in H-1/H-2 would never fail
a pull-request check.

---

## Medium findings

### M-5 — `verify_v6_audit.py` evidence validation is too weak
Lines 74–77 validate `source_files` / `test_references` / `verification_evidence` only for
verified IDs starting with `E/X/Y/W/D/V/Z`; verified base rows (`A*`, `B*`, `C*`) are
exempt. It also checks only that fields are non-empty — not that paths exist, that the
claimed module matches the feature, or that evidence text is feature-specific. This is why
H-3 escapes detection. Independently, all 268 verified rows currently have existing
source/test paths and non-empty evidence, so there is no present false-positive.

### M-6 — Source-hash regression test fails on Windows checkouts (portability)
```
cd keel && python -m pytest -q tests/test_plan_index.py tests/test_model_dialects.py ^
  tests/test_edit_formats.py tests/test_repo_map.py tests/test_steering.py ^
  tests/test_tool_contracts.py tests/test_tool_contracts_bridge.py tests/test_offline_runtime.py
```
Result: `1 failed, 211 passed, 1 skipped in 7.11s`. The failure is
`test_authoritative_source_hashes_unchanged`: working-tree bytes are CRLF
(`sha=47b346bc…`) while the pinned hash expects LF (`da1dd5dc…`). `core.autocrlf=true` and
no `.gitattributes` in this repo. **The git blobs themselves match the recorded hashes
exactly** (verified with `git show HEAD:<path>`), so the sources are genuinely preserved;
the test just hashes working-tree bytes and is platform-dependent. CI runs on Ubuntu so it
would pass there, but it fails on the Windows host that produced this work.

### M-7 — Owner-gated rows marked `verified` without gate-resolution evidence
`owner_approval_required: true` on `B6.6`, `C11.5`, `C11.8`, yet all three are
`verified` (tiers `external_dependency`, `operational`, `external_dependency`). Only
`C11.1`/`C11.2` are `blocked`/`owner_gated`. `DECISIONS.md` D-035 still records D1
("final EULA text needs owner's legal name, governing law, lawyer review", gate G5) as
open, while `C11.5` (EULA acceptance) is verified. The ledger's honesty note discloses that
legal texts are drafts pending owner review, so this is an ambiguity rather than a
fabrication, but the registry conflates "local mechanism verified" with "owner gate
cleared", and no gate checks `owner_approval_required` against `status`.

---

## Low / informational

- **L-8 — Two unrelated `parity.json` files.** Root `parity.json` is the 865-row registry
  projection; `keel/docs/parity.json` is an OpenCode upstream inspection report
  (different schema, `generatedAt 2026-11-18`). The verifier checks the root copy. Naming
  collision could mislead a reviewer.
- **L-9 — Hard-coded absolute paths** (`C:\Users\Admin\Desktop\Claude clone\…` in
  `build_dependency_graph.py`, `C:\Users\Admin\Downloads` fallback in
  `build_plan_index.py` / `build_v6_plan.py`). The in-repo copies are preferred, so those
  two generators are reproducible here; the dependency graph is not (see H-1).
- **L-10 — Source-hash pinning covers only the 3 base documents.** Addenda 3–7 have no
  recorded original hashes; only their git blobs can be inspected. Working-tree CRLF
  differs from the recorded LF hashes for the 3 base docs; blob-level equality confirmed.
- **L-11 — Historical ledger lines labelled "final"** in `IMPLEMENTATION-PROGRESS.md`
  (L656–659 "final registry status" 226/2/0; L700–704 tier counts 49/45/109/23/2) are
  superseded by the final state. The document labels the following narrative as a v5-era
  log, but the "final" headers are misleading.
- **L-12 — P0 share is 27.7%** (240/865), inside `verify_v6_audit.py`'s 22–30% band but
  above the ~25% target from X0.1; `RISKS.md` M0-R2 acknowledges this explicitly.

---

## Challenge-by-challenge results

1. **865 IDs exactly once / per-source counts — PASS.** Independent script: 865 IDs,
   `len(ids)==len(set(ids))` true; counts 133/95/132/128/114/123/140 exactly. The 8th
   source (`Keel_Master_Plan_v5.md`) has 0 feature rows by design and is documented in
   `base-verification.json` (`feature_rows: 0`, "master plan (non-feature requirements)").
2. **P0 re-ranking honest/reproducible — PASS.** 129 values changed: 93 `P0→P1`
   demotions, 36 invalid/empty source priorities normalized to `P1`; no promotions.
   Re-applying `_rerank_priorities` to every row gives 0 mismatches. `original_priority`
   preserves source values verbatim, including 36 non-standard values (`''`, `n/a`,
   `sdk`, `M3, M5`, `M22`). Caveat: H-3 (evidence misattribution).
3. **Sources verbatim / 20-row spot-check — PASS.** Git blobs of all 3 hashed base docs
   match recorded SHA-256. 20 sampled rows across all 7 feature sources matched extracted
   JSON priority/milestone/`original_priority` to the markdown tables. Full 865-row
   priority comparison: 0 substantive mismatches (5 rows carry the source's own odd
   values, faithfully preserved).
4. **Generated files actually generated — PARTIAL.** `PLAN-INDEX.json`, `parity.json`,
   `Keel_Master_Plan_v6.md` and `P0-BATCHES.md` regenerate byte-identically (monkeypatched
   temp outputs, SHA-256 equal). `DEPENDENCY-GRAPH.md` is stale (H-1).
5. **Governance docs — MOSTLY PASS.** No invented license facts (all model/voice entries
   `UNKNOWN` + `MUST VERIFY`; Work Sans OFL is sourced); dates consistent (2026-11-23
   compilation, 2026-07-28 MCP spec); `DECISIONS.md` 35 decisions/4 owner-gated verified;
   owner gates marked "awaiting owner"; no machine-readable stop-list falsely claimed as
   implemented (`X10.4` is `not_started`). Caveats: H-2, M-7.
6. **Offline CI + license gate — PASS.** Workflow exits 1 when `unshare` is absent
   (`set -euo pipefail` + explicit check); provider keys unset; local fake model. Synthetic
   gate test: baseline exit 0 (11 entries, 0 bundled); bundled non-commercial exit 1,
   no-redistribution exit 1, empty `verified_date` exit 1, `ci_gate:false` exit 1,
   fully-compliant bundled exit 0, policy-rule-removed exit 1. Gate genuinely fails closed.
   Caveat: H-4 (the other gates are not in CI).
7. **Status honesty — PARTIAL.** Registry and final matrix JSON/CSV report
   `595 not_started / 268 verified / 2 blocked` exactly. Human-facing matrix, graph, risk
   register and status/amendment docs report 226/637 (H-2).

---

## Exact commands and results (reproduction)

```
python scripts/verify_v6_audit.py
  -> registry rows: 865; P0 share 27.7%; matrix rows 865; CONSISTENCY OK; EXIT=0

python keel/scripts/build_dependency_graph.py --check
  -> STALE: ...\DEPENDENCY-GRAPH.md; EXIT=1

python scripts/check_model_licenses.py
  -> license registry: 11 entries, 0 bundled; LICENSE GATE OK; EXIT=0

python keel/scripts/build_dependency_graph.py --plan <worktree>\PLAN-INDEX.json --output <temp>\depgraph_regen.md
  -> 363 lines; diff vs committed: 41 insertions, 51 deletions

python <temp>\spotcheck_extract.py
  -> 20 sampled rows across 7 sources: all OK; full priority mismatches: 0 substantive

python <temp>\regen_check.py
  -> PLAN-INDEX.json IDENTICAL; parity.json IDENTICAL;
     Keel_Master_Plan_v6.md IDENTICAL; P0-BATCHES.md IDENTICAL

python <temp>\license_gate_synth.py
  -> all 6 synthetic cases behaved as expected (see challenge 6)

cd keel && python -m pytest -q <audit + X1 + tool-contract + offline tests>
  -> 1 failed (source-hash CRLF portability), 211 passed, 1 skipped
```

---

## Recommended remediation priority (not applied — review only)

1. Regenerate `DEPENDENCY-GRAPH.md` after the final verification marks and fix the
   generator's hardcoded paths / stale default extract path; add `--check` to CI.
2. Regenerate/refresh `REMAINING-WORK-MATRIX.md`, `RISKS.md`,
   `ADDENDA-OPERATION-STATUS.md` and the amendment to 268/595/2; add a CI assertion that
   those documents' headline counts match `PLAN-INDEX.json`.
3. Fix `_load_extra_features()` to write the per-group `src_files` / `test_files` /
   `evidence` locals instead of the unconditional `TOOL_CONTRACT_*` constants, then
   regenerate `PLAN-INDEX.json`, `parity.json`, `Keel_Master_Plan_v6.md` and the matrix.
4. Wire `verify_v6_audit.py` into a workflow; strengthen it to validate path existence,
   evidence-to-feature correspondence, all verified prefixes, and owner-gate/status
   consistency.
5. Make `test_authoritative_source_hashes_unchanged` read git blobs (or normalize CRLF)
   so it passes on Windows; optionally pin hashes for addenda 3–7.
