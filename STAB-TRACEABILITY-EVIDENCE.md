# STAB-TRACEABILITY-EVIDENCE.md — requirement-traceability audit

**Verdict:** the numeric core of all six audited requirements reproduces on the current
main-derived tree. Canonical registry, 421-ID backend attribution, `--strict` enforcement,
reasons for the 11 open rows, acceptance criteria and evidence documents all check out.
The discrepancies found are **documentation/certification-layer** issues (stale or
self-contradictory prose, stale classification entries), not status inflation in the
canonical registry. They are listed first, as requested.

## 0. Scope, provenance, method

- Worktree: `C:\Users\Admin\.local\share\opencode\worktree\stab\trace`
- Branch: `agent/stab-trace`; HEAD `f60b080a1c770608e1ddbf3d888a6e63a7c1b6bb`
  (`docs(stabilization): record verified baseline and failing CI workflows`, 2026-11-25).
- Tree was clean before this audit (`git status --porcelain` empty). **No tracked source,
  registry, or document was edited.** The only new file is this evidence report.
- Probe method: full copy of the worktree (excluding `.git`) into
  `C:\Users\Admin\AppData\Local\Temp\opencode\stab-trace-probe` via `robocopy /E /XD .git`;
  all perturbations were made there and never in the audited worktree.
- Reproduce with:
  `python scripts/verify_backend_operation.py`,
  `python scripts/verify_backend_operation.py --strict`,
  `python scripts/verify_v6_audit.py`, plus the JSON/AST analyses summarized below.

---

## 1. Discrepancies (reported first)

### D1 — verifier docstring still denies the enforced behaviour (doc/code contradiction)

- `scripts/verify_backend_operation.py:11` correctly says
  `Evidence-based gate (REPORTED by default; ENFORCED with --strict)`.
- `scripts/verify_backend_operation.py:30-33` still says failures
  "do NOT change any status and **do NOT fail the script**; the lead decides what to do
  with them." This directly contradicts line 11 and the code:
  `strict = "--strict" in sys.argv` (`:452`), `if strict and gate_failures: errors.append(...)`
  (`:467-469`), and `raise SystemExit(1)` on any error (`:470-474`).
- Same stale claim in `REGISTRY-EVIDENCE-INTEGRITY.md:50-53`: "The gate is **reported, not
  enforced** ... does not alter any status and does not fail the script", while the same
  file's authoritative `FINAL AMENDMENT` at `:244-249` says `--strict` enforces a non-zero
  exit. The historical section 2/4 is not marked "historical" in place.
- Note: an earlier finding about the error text "(run without `--strict` to list them)"
  was already fixed — current `:468` reads "(see per-ID failures above)". Only the
  docstrings/prose remain wrong. No behaviour change is needed.

### D2 — W1.18 / Y6.4 mislabelled "owner-gated" in several documents

Canonical rows (`PLAN-INDEX.json`, confirmed byte-identical in `parity.json`):
W1.18 = `not_started` / `local_module` / `owner_approval_required=false` / no artifacts /
detail = LICENSE + vendor-license verification; Y6.4 = `not_started` / `local_module` /
`owner_approval_required=false` / `dependencies=["G1"]` / detail = public-repo observation.
Neither is `owner_gated` nor `blocked`, and neither is in the 421-ID attribution.

Still-contradicting statements:

- `FINAL-ENGINEERING-REPORT.md:32` and `:101` — "owner-gated conflicts".
- `BACKEND-OPERATION-TASKBOARD.md:22` — "2 owner-gated conflicts (W1.18/Y6.4)".
- `DECISIONS.md:52-53` (table rows D-036/D-037 "owner-gated (do not implement)"), `:55`
  ("4 require owner approval" while D-036/D-037 say "yes" at `:723`, `:731`), `:722`
  ("Record as owner-gated/blocked"), `:730` ("partially owner-gated").
- `master-plan-v6-agent-commit-index.md:46` and `master-plan-v6-agent-execution.md:98`.

Corrected statements already present: `BACKEND-COMPLETION-BACKLOG.md:26`,
`FINAL-ENGINEERING-REPORT.md:70`, `BACKEND-COMPLETION-ACCOUNTING.md:103-104`,
`REMAINING-WORK-MATRIX.md:54-55`, `PRODUCTION-REQUIREMENT-RECONCILIATION.md:141-149`.
These are rejections *as written*, not status/ownership changes.

### D3 — stale "361/421 traceable + 60 limited" figures still framed as current

Superseding `FINAL AMENDMENT` sections exist, but the older passages are not marked
historical in place:

- `AUDIT-REMEDIATION-SUMMARY.md:13` and `:45` (amendment at `:60-73`).
- `REGISTRY-EVIDENCE-INTEGRITY.md:127-140` ("Results of the gate ... run of this branch",
  361 pass / 60 fail; amendment at `:244-257`).
- `REMAINING-WORK-MATRIX.md:21-24` and `:64-89` (amendment at `:134-147`).
- `master-plan-v6-test-evidence.md:150` and `:161` (amendment at `:174-184`).
- `BACKEND-COMPLETION-ACCOUNTING.md:107-108` — "The **60 certification-limited rows**
  ... reduce `completion_backend_certified` only", contradicting its own §3 (`:56-57`,
  `L_B = 0`) and amendment (`:136-149`). (Its `:77` is correctly marked historical.)
- By contrast `FINAL-ENGINEERING-REPORT.md:190-191` now carries inline `HISTORICAL`
  markers and is not a live contradiction.

Current measured value is **421 passing / 0 failing** (Section 3 below), so all 361/60
figures are historical only.

### D4 — `promotion-classification.json` has 8 entries for paths absent from the tree

The file has 458 classified paths and a `candidate` value
`release/backend-production-readiness-2026-11-24-v2`, matching
`PRODUCTION-PROMOTION-MANIFEST.md:488`. All 20 backend modules are correctly
`PLAN_BACKEND_IMPLEMENTATION`, all 65 `master-plan-v6-*-evidence.md` paths are
`BACKEND_DOCUMENTATION`, `Cargo.toml` is `REQUIRED_BACKEND_DEPENDENCY` (`:71`) and
`check_version_sync.py` is `BACKEND_TEST_OR_CI` — earlier dual-classification defects are
fixed. However these 8 classified paths are neither tracked nor present on disk:

| File:line | Path | Class |
| :- | :- | :- |
| `promotion-classification.json:70` | `keel/_prod_suite_tmp.py` | BACKEND_DOCUMENTATION |
| `promotion-classification.json:88` | `keel/docs/research/external-readiness.md` | BACKEND_DOCUMENTATION |
| `promotion-classification.json:89` | `keel/docs/research/final-independent-audit.md` | BACKEND_DOCUMENTATION |
| `promotion-classification.json:99` | `keel/docs/research/remaining-work-matrix.md` | BACKEND_DOCUMENTATION |
| `promotion-classification.json:100` | `keel/docs/research/sandbox-conformance.md` | BACKEND_DOCUMENTATION |
| `promotion-classification.json:101` | `keel/docs/research/source-repository-register.md` | BACKEND_DOCUMENTATION |
| `promotion-classification.json:327` | `keel/tests/test_validation_script.py` | BACKEND_TEST_OR_CI |
| `promotion-classification.json:333` | `keel/tests/test_website_download_only.py` | BACKEND_TEST_OR_CI |

The last two are among the deliberately removed frontend test files documented at
`PRODUCTION-PROMOTION-MANIFEST.md:461-471`; the temp runner was deleted in commit
`b71b53d` but reclassified rather than removed from the JSON. The classification file is
therefore a stale candidate snapshot, not an exact inventory of the current tree.
Related stale audit claims (both written at earlier candidate SHAs):
`FINAL-ERROR-SWEEP.md:126` says the JSON has 383 entries (actual 458);
`FINAL-RELEASE-ACCEPTANCE.md:35` says 383 (actual 458). Also
`PRODUCTION-PROMOTION-MANIFEST.md:489` still contains the unresolved literal
`CANDIDATE_HEADd0994986223dd802e47a078a0aeaf5203` instead of a plain 40-hex SHA.

### D5 — over-precise remediation claim about `FEATURE_TRACEABILITY` / per-ID rows

Five `FINAL AMENDMENT`s (e.g. `REGISTRY-EVIDENCE-INTEGRITY.md:246-248`,
`BACKEND-COMPLETION-ACCOUNTING.md:138-140`, `FINAL-ENGINEERING-REPORT.md:204-206`,
`AUDIT-REMEDIATION-SUMMARY.md:62-63`, `REMAINING-WORK-MATRIX.md:136-137`,
`master-plan-v6-test-evidence.md:173-174`, `BACKEND-IMPLEMENTATION-DETAIL.md:78-79`)
say the batch "added AST-visible `FEATURE_TRACEABILITY` declarations and per-ID evidence
rows to **every owning module**". Measured on the current tree:

- only **4 of 20** modules literally contain the identifier `FEATURE_TRACEABILITY`
  (`d6_reliability_backend`, `e6_x5_x6_backend`, `w7_x1_y5_d1_backend`, `y2_backend`);
  the others certify IDs through other AST constructs (`FEATURE_IDS` collections, dict
  keys) or through evidence rows.
- only **12 of 20** modules have per-ID evidence rows that resolve to a real symbol and a
  real test (218 of 421 IDs); 8 modules have no such rows and pass via the module/test AST
  path (203 IDs).

This is an imprecise description of the mechanism, **not** a false 421/421 claim: the gate
genuinely passes all 421 IDs (Section 3). No status is inflated by it.

### D6 — minor tier wording slip

`BACKEND-COMPLETION-ACCOUNTING.md:48` says "W1.18 and Y6.4 are local_module/operational";
both canonical rows are `local_module` (neither is `operational`).

### D7 — stale secondary matrix presented as a registry source

`master-plan-v6-final-matrix.json` still reports `verified: 433 / not_started: 430 /
blocked: 2` (865 rows), versus the canonical `854 / 9 / 2`. It is referenced as an
"865-row registry" source of requirements at
`master-plan-v6-config-contracts-evidence.md:5` and listed as plan-registry documentation
at `PRODUCTION-PROMOTION-MANIFEST.md:358`; `REVIEW-PLANNING-FINDINGS.md:95` says
`PLAN-INDEX.json`, the final matrix and `.csv` "all report" the same figures. The
authoritative file is `PLAN-INDEX.json` / `parity.json`; the final matrix is a stale
plan-era artifact and should not be quoted for status.

---

## 2. Requirement 1 — 865 canonical IDs, status split, parity, SHA

| Check | Result |
| :- | :- |
| `PLAN-INDEX.json` features | **865** rows, **865** unique IDs |
| Status counts | **854 verified / 9 not_started / 2 blocked** |
| Priority counts | P1 524 / P0 240 / P2 101 |
| `parity.json` vs `PLAN-INDEX.json` | **byte-identical** (same SHA-256, same bytes) |
| `verify_v6_audit.py` | `CONSISTENCY OK`, 865 rows, exit 0 |
| Verified rows with empty source/test/evidence | 0 / 854 |
| Non-verified rows carrying implementation artifacts | 0 |

SHA-256 (both files):
`62fd5c6ac2d166e8cb1f5752c168d22d56d767c7e6a5bf9384696756a4a5b2f6`.
Every full-SHA citation in the top-level docs matches this value; the only abbreviated
form is `REGISTRY-EVIDENCE-INTEGRITY.md:239`, explicitly labelled "SHA-256 prefix".
`Keel_Master_Plan_v6.md` SHA-256 begins `312d61782dd19a94` as quoted at
`REGISTRY-EVIDENCE-INTEGRITY.md:240`.

The 9 `not_started` IDs are `D6.14, D6.17, D6.18, D6.2, D6.20, D6.21, D6.23, W1.18,
Y6.4`; the 2 `blocked` IDs are `C11.1, C11.2`. **Confirmed**, except for stale secondary
artifact D7.

## 3. Requirement 2 — 421 backend-attributed IDs, 20 modules, consistency

- `backend-final-attribution.json:attribution` has **421** keys, 421 unique, mapped to
  **20** module values (evidence_docs also has 20 entries). Per-module counts
  (`BACKEND-IMPLEMENTATION-DETAIL.md:7-26` sum = 421):

  d3 13 · d6 18 · d7 16 · e3 13 · e5 13 · e6/x5/x6 27 · e7 36 · small_groups 54 ·
  v_series 24 · w1 16 · w4 13 · w7/x1/y5/d1 32 · x2 16 · x3 16 · x8 15 · y1 25 ·
  y2 15 · y3 13 · y4/d4/x7 31 · z 15 = **421**.

- `backend_hub.modules()` = 20; `backend_hub.feature_ids()` = 421 and its set **equals**
  the attribution key set; `FEATURE_TO_MODULE[id] == attribution[id]` for all 421
  (**0 mismatches**). Capabilities registered: `backend.modules`, `backend.describe`,
  `backend.invoke`, `backend.verify`. All attributed rows are `verified`.
  → **no false cross-attribution**.

- `backend-module-id-coverage.json`: 20 `per_module` lists (sum 489 with cross-references),
  `combined` = 477 unique IDs = the union of `per_module`. `attribution - combined = []`
  (all 421 are declared in their module); `combined - attribution = 56` cross-module/prose
  IDs (e.g. `W1.18`, `Y6.4`, `C11.1`, `D3.1`, `V1`), correctly **not** used as the
  denominator. `missing_not_started` = exactly the seven D6 IDs above, all
  `not_started`/`local_module`/not attributed.

- `promotion-classification.json`: 458 entries; all 20 backend modules and all 65
  evidence docs classified as described in D4. Content is consistent with the backend
  claims, with the 8 stale paths of D4 being the only current-tree mismatch.

## 4. Requirement 3 — `scripts/verify_backend_operation.py --strict`

**Code inspection (current file):**

- `:51-56` loads both registry files and fails on `index != parity`, wrong length or
  duplicate IDs; `:62-64` enforces exactly `{verified:854, not_started:9, blocked:2}`;
  `:66-69` enforces 421 attribution keys.
- `:82-97` checks every attributed ID is in the registry, `verified`, has existing
  source/test paths and an existing evidence doc with non-empty `verification_evidence`.
- `:99-126` enforces 20 hub modules, hub index containing all attributed IDs, four
  `backend.*` capabilities, successful imports and six operation documents.
- `:398-441` iterates **all 421** `attribution.items()` and checks, per ID:
  module AST construct or valid evidence-table cross-check (`:418-422`), test AST
  reference or cross-check (`:424-430`), non-empty `acceptance_criteria` (`:432-433`),
  evidence doc exists and contains the literal ID (`:435-438`).
- `:452` `strict = "--strict" in sys.argv`; `:463-465` prints ENFORCED/reported mode;
  `:467-469` appends an error when `strict and gate_failures`; `:470-474` exits 1 on any
  error. Non-strict runs report failures but exit 0. The docstring contradiction is D1.

**Live runs on the audited tree:**

| Run | Gate output | Exit |
| :- | :- | :-: |
| no flag | audited 421, passing 421, failing 0, `BACKEND OPERATION VERIFICATION OK` | 0 |
| `--strict` | `EVIDENCE-BASED GATE (ENFORCED)`, audited 421, passing 421, failing 0, `VERIFICATION OK` | 0 |

**Temporary-copy probes (no worktree file touched):**

| Perturbation in temp copy | Mode | Result | Exit |
| :- | :- | :- | :-: |
| none (control) | `--strict` | passing 421, failing 0 | 0 |
| removed the `| Y5.7 | ... |` evidence row from temp copy of `master-plan-v6-w7-x1-y5-d1-backend-evidence.md:92` | no flag | `passing 420, failing 1`; `Y5.7`: no AST construct/evidence row + doc does not mention ID; still `VERIFICATION OK` | 0 |
| same perturbed copy | `--strict` | `1 attributed IDs fail the evidence gate`, `VERIFICATION FAILED` | **1** |
| evidence row restored; `acceptance_criteria` cleared for `D7.7` in both registry copies | `--strict` | `1 x acceptance_criteria empty`, `VERIFICATION FAILED` | **1** |

Conclusion: `--strict` genuinely enforces **all 421** evidence checks with a non-zero exit
on failure. The only defect is the stale documentation described in D1.

## 5. Requirement 4 — honest reasons for the 9 + 2 open rows

| ID(s) | Canonical status / tier / owner | Documented reason and location |
| :- | :- | :- |
| Seven D6: `D6.14, D6.17, D6.18, D6.2, D6.20, D6.21, D6.23` | `not_started` / `local_module` / false; no artifacts; in `missing_not_started`, not attributed | Builder-constitution conventions (Review / Convention / Review / Doc-sync gate / Builder rule / Template / Doc), Add.6 §7 — `REMAINING-WORK-MATRIX.md:41-53`, `BACKEND-COMPLETION-ACCOUNTING.md:98-102`, `BACKEND-OPERATION-TASKBOARD.md:22` |
| `W1.18` | `not_started` / `local_module` / false; no artifacts | License + `vendor/` notices verification; decision rejects MIT-as-written but does not change status — `REMAINING-WORK-MATRIX.md:54`, `BACKEND-COMPLETION-ACCOUNTING.md:103-104`, `BACKEND-COMPLETION-BACKLOG.md:26` (contradictions in D2) |
| `Y6.4` | `not_started` / `local_module` / false; `dependencies=["G1"]`; no artifacts | External repository-visibility observation, gated by G1, not a local implementation — `REMAINING-WORK-MATRIX.md:55`, `BACKEND-COMPLETION-ACCOUNTING.md:103-104` (contradictions in D2) |
| `C11.1` | `blocked` / `owner_gated` / true; no artifacts | Owner decision on source hosting, gate G6 — `REMAINING-WORK-MATRIX.md:61`, `PRODUCTION-REQUIREMENT-RECONCILIATION.md:143` |
| `C11.2` | `blocked` / `owner_gated` / true; no artifacts | GitHub Free private-repo security hygiene (2FA, branch protection, signed commits), owner/plan decision — `REMAINING-WORK-MATRIX.md:62`, `PRODUCTION-REQUIREMENT-RECONCILIATION.md:144` |

Named exceptional IDs are consistently documented as: `C11.5` verified / `operational` /
owner flag true; `C11.8` verified / `external_dependency` / true; `B4.8` verified /
`external_dependency` / false; `B6.6` verified / `external_dependency` / true —
`REMAINING-WORK-MATRIX.md:96-102` and `PRODUCTION-REQUIREMENT-RECONCILIATION.md:145-149`.
None of these nine excluded rows is in the 421 attribution. **Verdict:** reasons are
honest and mostly consistent; W1.18/Y6.4 prose mislabels remain as D2, and D6's tier
wording slip is D6.

## 6. Requirement 5 — acceptance criteria and evidence documents

- All **421** attributed rows have non-empty `acceptance_criteria` (0 empty; verified both
  directly and by the gate at `verify_backend_operation.py:432-433`). Distribution: 297
  rows with 1 criterion, 28 with 2, 2 with 3, 94 with 4. **93** of the 421 carry criteria
  explicitly prefixed `[DERIVED - source omitted acceptance criteria]` (e.g. `X6.4`,
  `X6.9`), matching `REGISTRY-EVIDENCE-INTEGRITY.md:36-44` and the "93 → 0" remediation.
- All 421 rows have non-empty `verification_evidence`; each named evidence doc exists and
  contains the literal ID (gate check `:435-438`).
- All **20** evidence docs contain backticked identifiers that resolve to real AST
  definitions (module function/class/method/assignment or real `test*` function) —
  verified per document. **218** IDs have a per-ID evidence-table row naming a real symbol
  *and* a real test; the other **203** are certified via module/test AST constructs
  (e.g. `D7.*` via `d7_workflow_backend.FEATURE_IDS`; `X8.8` via
  `test_x8_8_thread_index_*`). Examples of real artifacts: `Y5.7` → `channel_status`,
  `gateway_start`, `test_y5_7_status_and_gateway_commands`
  (`master-plan-v6-w7-x1-y5-d1-backend-evidence.md:92`); `X6.4` derived criteria name
  `e6_x5_x6_backend`, its module/test paths and evidence doc.
- **Verdict:** acceptance criteria present for all 421, and evidence docs reference real
  symbols/tests. The 203/218 split is the mechanism nuance recorded in D5, not a gap.

## 7. Requirement 6 — status inflation / contradictory claims

- **No status inflation found in the canonical registry or the 421-ID attribution:**
  counts are 854/9/2 and 421/421 verified; no open row was promoted; no attributed ID is
  non-verified; no excluded row is silently attributed; all 20 hub modules and 4
  capabilities are real and importable. The 100.0% figures in
  `BACKEND-COMPLETION-ACCOUNTING.md:62,73,129-130` are correctly scoped to the 421-ID
  backend denominator and expressly not production-readiness claims (`:65-67`, `:132-133`).
- Contradictory/stale claims are D1–D7 above, each with file:line.
- No canonical status or owner decision was changed by this audit.
