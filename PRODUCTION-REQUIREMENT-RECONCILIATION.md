# Production requirement reconciliation — read-only audit (2026-11-24)

**Scope:** reconcile the inventories and classifications in `BACKEND-COMPLETION-ACCOUNTING.md`,
`BACKEND-COMPLETION-BACKLOG.md`, `BACKEND-OPERATION-TASKBOARD.md`,
`FINAL-ENGINEERING-REPORT.md`, `REMAINING-WORK-MATRIX.md`, `PLAN-INDEX.json`, `parity.json`,
`backend-final-attribution.json`, `backend-module-id-coverage.json`, and
`PRODUCTION-PROMOTION-MANIFEST.md`. No tracked source or registry status was changed.

**Provenance of this audit**

- Worktree: `C:\Users\Admin\.local\share\opencode\worktree\production\trace`, branch `agent/prod-trace`,
  working HEAD `e6e7efc` ("build(release): create production candidate with classified backend-only promotion from origin/main").
- The task names candidate HEAD `e573273`. That commit exists, but is on
  `release/backend-production-readiness-2026-11-24`, **not** on `agent/prod-trace`. Its only deltas from
  `e6e7efc` are (a) `keel/desktop/src-tauri/Cargo.toml` `0.1.0` -> `0.1.1` and (b) the appended
  "Explicit scope exception" in `PRODUCTION-PROMOTION-MANIFEST.md`. All other audited files are
  byte-identical between the two commits. The candidate's manifest exception was read with
  `git show e573273:PRODUCTION-PROMOTION-MANIFEST.md` and is audited below. **Lead should confirm which
  commit is the promotion candidate**, because the checked-out branch does not contain its two changes.

---

## 1. Contradictions requiring lead correction (reported first)

### C1 — W1.18 and Y6.4 are called "owner-gated conflicts" but the canonical registry says otherwise

Canonical registry rows (authoritative `PLAN-INDEX.json`, SHA-256
`62fd5c6ac2d166e8cb1f5752c168d22d56d767c7e6a5bf9384696756a4a5b2f6`):

| ID | `status` | `implementation_tier` | `owner_approval_required` | `dependencies` |
| :- | :- | :- | :-: | :- |
| W1.18 | `not_started` | `local_module` | `false` | `[]` |
| Y6.4 | `not_started` | `local_module` | `false` | `["G1"]` |

Neither row is an owner-gated row: `owner_gated` tier is held only by C11.1/C11.2, and the registry's
`owner_approval_required` flag is `false` for both. Y6.4 has a **G1 dependency**, which is a dependency,
not an ownership tier.

Contradicting statements found:

- `BACKEND-COMPLETION-BACKLOG.md` line 26: "W1.18 (MIT license), Y6.4 (public repo): **owner-gated
  conflicts** D-036/D-037."
- `FINAL-ENGINEERING-REPORT.md` line 32: "The only 2 not-started P0 rows are **owner-gated conflicts**
  REJECTED via DECISIONS.md D-036/D-037".
- `FINAL-ENGINEERING-REPORT.md` line 70: "plus 2 **owner-gated conflicts** (W1.18 MIT license, Y6.4
  public repo — DECISIONS D-036/D-037)".
- `FINAL-ENGINEERING-REPORT.md` line 101: "W1.18/Y6.4: **owner-gated conflicts** with
  private/proprietary requirements (owner decision)."
- Supporting evidence `DECISIONS.md` D-036 line 722 records "Record as **owner-gated/blocked**" and
  D-037 line 730 "partially owner-gated", with "Owner approval required: yes" (lines 723, 731),
  while the canonical rows keep `not_started` / `local_module` / `owner_approval_required=false`.
  `DECISIONS.md` line 55 is also internally inconsistent: it states only 4 decisions require owner
  approval (D-005, D-007, D-034, D-035) although D-036/D-037 say "yes".

Correct reconciliation (already stated in `BACKEND-COMPLETION-ACCOUNTING.md` §2/§4 and
`REMAINING-WORK-MATRIX.md` §3): W1.18/Y6.4 are **in-scope `not_started`** rows — a licensing/notices
verification task and an external repository observation (Y6.4 gated by dependency G1) — **not**
owner-gated and not backend-attributed. The decision records are a refusal to implement *as written*;
they do not change registry status or ownership. **Lead correction:** change the four prose labels above
(and, if desired, reconcile `DECISIONS.md` D-036/D-037/line 55) to "REJECTED as written; still
`not_started`, `local_module`, `owner_approval_required=false`; Y6.4 depends on G1". Do **not** change
the registry to `blocked`/`owner_gated` merely to match the prose.

### C2 — Candidate manifest classifies `keel/desktop/src-tauri/Cargo.toml` twice, incompatibly

In candidate `e573273`:

- Path table line 67 still says
  `| keel/desktop/src-tauri/Cargo.toml | UNRELATED_EXCLUDED | ... | exclude | n/a (excluded) |`.
- Appended section "Explicit scope exception — required version-sync constant" (lines 412-419) says the
  same path "is classified **`REQUIRED_BACKEND_DEPENDENCY`**" and must be included for the version gate.

The technical rationale is correct and was independently verified: `keel/release/common.py::load_versions`
reads seven files; at `e6e7efc` six are `0.1.1` and `desktop/src-tauri/Cargo.toml` is `0.1.0`, so
`validate_version()` raises `VERSION MISMATCH`; `keel/tests/test_signing_gate.py` line 28 calls
`common.validate_version()` at module scope, so collection fails. Candidate `e573273` bumps that one
string to `0.1.1`, which resolves it. **Lead correction:** update line 67 of the manifest to
`REQUIRED_BACKEND_DEPENDENCY` with a reason cross-referencing the exception (or delete the exception if
the path really is to be excluded); the document cannot simultaneously say "exclude" and "include".

### C3 — Stale 361/421 and 60-failure figures are still presented as current

The FINAL AMENDMENT sections authoritatively supersede them with 421/421 traceable, 0 limitation, but
the earlier sections are not marked historical in place:

- `FINAL-ENGINEERING-REPORT.md` lines 176-199 ("Additive reconciliation amendment (no result changed)")
  state at lines 189-192: "only **361 / 421 = 85.7%** fully traceable and **60 / 421 = 14.3%** verified
  with certification limitation". The same document's FINAL AMENDMENT (lines 202-215) says those figures
  are historical and current certification is 421/421 / 0. Internal contradiction.
- `REMAINING-WORK-MATRIX.md` §5 lines 64-89 state "**Result: 361 pass, 60 fail at least one check**",
  include the 60-ID table and "62 check-failures across 60 IDs" as the live gate result, without an
  in-place historical marker; the FINAL AMENDMENT at lines 134-147 contradicts it.
- `BACKEND-COMPLETION-ACCOUNTING.md` §4 lines 107-108 still say "The **60 certification-limited rows**
  are not reclassified ... they reduce `completion_backend_certified` only"; its own FINAL AMENDMENT
  (lines 136-152) and §3 (`L_B = 0`, limitation rate 0.0%) say there are none now. §3 line 77 does mark
  the list historical; §4 does not.
- `BACKEND-IMPLEMENTATION-DETAIL.md` line 62 likewise still says "certification limitation ... certifies
  **361 / 421**", despite its FINAL AMENDMENT at lines 76-88.

**Lead correction:** insert an in-place "historical, superseded by FINAL AMENDMENT — current value
421/421 (0 limited)" note at each stale passage, or replace the figures with the current ones. The
FINAL AMENDMENTs themselves are consistent with the verified gate result and should be kept.

### C4 — `scripts/verify_backend_operation.py` docstring contradicts the enforced `--strict` behavior

The code is correct and enforces all 421 IDs (see §3 below), but its documentation says the opposite:

- Module docstring line 11: "Evidence-based gate (**REPORTED, never auto-enforced**)".
- Lines 30-33: "failures ... **do NOT change any status and do NOT fail the script**; the lead decides
  what to do with them."

Actual behavior: line 452 `strict = "--strict" in sys.argv`; lines 467-474 append an error and
`raise SystemExit(1)` when `strict and gate_failures`. The printed output at lines 453-465 correctly
says "ENFORCED" and "failures cause a non-zero exit" in strict mode. Also line 468's error text
"(run without `--strict` to list them)" is inaccurate: per-ID failures are printed unconditionally at
lines 460-462, including under `--strict`. **Lead correction:** rewrite the docstring to describe
default (report-only) *and* strict (enforced, non-zero exit) modes and fix the parenthetical. No
behavior change is needed. (CLI note: `strict` is detected by substring membership in `sys.argv`, not
an argparse flag; `--strict` works as intended.)

### C5 — Multiple "definitive" full-suite figures in one composite report (clarification, not a status error)

`FINAL-ENGINEERING-REPORT.md` line 166 calls 4071 passed "Definitive final clean-environment" and
line 248 calls 4214 passed "Definitive full suite". Both figures are supported by
`master-plan-v6-test-evidence.md` (lines 139-142 and 189-210) but belong to different appended
operations (adversarial audit vs backend-completion delivery). The report is a concatenation of
sections that also alternate between "no push performed" (lines 9, 35) and "push verification"
(lines 220-252). **Lead correction:** label each section's operation and designate one authoritative
final figure for the promotion candidate (4214 passed / 48 skipped / 0 failed) to avoid readers
quoting an older stage.

---

## 2. Canonical status / ownership of the named IDs

Source: `PLAN-INDEX.json` v2, SHA-256 `62fd5c6ac2d166e8cb1f5752c168d22d56d767c7e6a5bf9384696756a4a5b2f6`.
No status or owner decision is invented here; "doc agreement" refers only to the ten reconciled files.

| ID | Canonical `status` | `implementation_tier` | `owner_approval_required` | Other canonical facts | Canonical classification | Doc agreement |
| :- | :- | :- | :-: | :- | :- | :- |
| **W1.18** | `not_started` | `local_module` | `false` | P0, M0; no `source_files`/`test_references`; `detail` = same-notices/LICENSE verification | In-scope `not_started`; licensing/notices verification; not backend-attributed | ACCOUNTING §2/§4 and MATRIX §3 agree; BACKLOG L26 and FINAL L32/L70/L101 mislabel "owner-gated" (C1) |
| **Y6.4** | `not_started` | `local_module` | `false` | P0, M1; `dependencies=["G1"]`; no implementation artifacts | In-scope `not_started`; external repo observation gated by dependency G1; not backend-attributed | ACCOUNTING §2/§4 and MATRIX §3 agree; BACKLOG L26 and FINAL L32/L70/L101 mislabel "owner-gated" (C1) |
| **C11.1** | `blocked` | `owner_gated` | `true` | P0, M1; gate G6; no artifacts | Owner-gated `blocked`; excluded from applicable/backend denominator | All docs agree (ACCOUNTING §2, MATRIX §4/§6, FINAL C/G) |
| **C11.2** | `blocked` | `owner_gated` | `true` | P0, M1; GitHub Free plan/2FA gates; no artifacts | Owner-gated `blocked`; excluded | All docs agree |
| **C11.5** | `verified` | `operational` | `true` | P0, M1; `src/keel/eula.py` + `tests/test_eula.py` | Verified with owner-approval flag; excluded from backend denominator by ACCOUNTING §2/MATRIX §6 "owner-gated (3)" class — by the **flag**, not by tier (tier is `operational`) | Docs agree on flag; note the class is flag-based, whereas C11.8/B6.6 (also flag `true`) are classed by tier as external. Undocumented precedence; recommend spelling out "tier first, then flag" |
| **C11.8** | `verified` | `external_dependency` | `true` | P1, M22; deterrent obfuscation; `platform_gaps.py` | External-dependency `verified`; excluded | ACCOUNTING §2 and MATRIX §6 agree (classed by tier). Flag `true` is not mentioned there; not a contradiction if tier-first rule is stated |
| **B4.8** | `verified` | `external_dependency` | `false` | P2, M20; LAN/QR pairing, pinned TLS; phone reachability external | External-dependency `verified`; excluded | Agree |
| **B6.6** | `verified` | `external_dependency` | `true` | P2, M24; per-org audit export/retention | External-dependency `verified`; excluded | Agree (same tier-first note as C11.8) |
| **Seven D6 conventions** — D6.14, D6.17, D6.18, D6.2, D6.20, D6.21, D6.23 | `not_started` | `local_module` | `false` | All P1, M0, Add.6 §7; `detail` = Review/Convention/Doc-sync gate/Review/Builder rule/Template/Doc; no artifacts | In-scope `not_started` builder-convention rules; listed in `backend-module-id-coverage.json` `missing_not_started`; **not** in the 421 attribution | ACCOUNTING §2/§4, MATRIX §3, TASKBOARD, BACKLOG agree exactly |

The nine excluded verified/blocked rows are C11.1, C11.2, C11.5, B4.8, B6.6, C11.8, B6.2, B6.3,
B6.5. **None appears in `backend-final-attribution.json`** (checked directly), confirming ACCOUNTING §2's
"none of the 9 appears in the 421 backend-attributed set".

---

## 3. Verification results (all checks reproduced)

### 3.1 865 IDs / 854 / 9 / 2 / parity identical — CONFIRMED

- `PLAN-INDEX.json`: 865 rows, 865 unique IDs, `status = {verified: 854, not_started: 9, blocked: 2}`,
  `priority = {P1: 524, P0: 240, P2: 101}`. SHA-256 equals the value quoted in all four docs.
- `parity.json` is **byte-identical** to `PLAN-INDEX.json` (same SHA-256), so "parity identical" holds for
  the canonical registry pair used by both verifiers. (`keel/docs/parity.json` is an unrelated
  upstream-opencode parity artifact; it is not the file the docs' claim refers to.)
- `python scripts/verify_v6_audit.py` -> `CONSISTENCY OK`, exit 0 (matches FINAL L249).
- `python keel/scripts/build_dependency_graph.py --check` -> `FRESH`, exit 0 (matches FINAL L251).
- `python scripts/check_model_licenses.py` -> `LICENSE GATE OK`, exit 0 (matches FINAL L251).
- 8 `.github/workflows/*.yml` files parse as YAML; no `uses:` ref lacks a full 40-hex SHA (matches FINAL L251).
- `feature-checklist.md` cross-inventory note checked: it declares **398** rows (line 78) and its
  rendered tables contain **410** unique contract IDs (409 `S<n>-<WORD>-<nnn>` plus `S2-ENV-016A`).
  ACCOUNTING §5's "398 declared / 410 unique, non-additive" is accurate.

### 3.2 421 backend-attributed IDs exactly — CONFIRMED

- `backend-final-attribution.json.attribution`: **421 keys, 421 unique, 20 module values**, zero duplicates.
- Every attributed ID exists in the registry and is `verified`; every module count matches
  `BACKEND-IMPLEMENTATION-DETAIL.md`'s per-module table (13+18+16+13+13+27+36+54+24+16+13+32+16+16+
  15+25+15+13+31+15 = **421**) and `backend-final-attribution.json`'s counts exactly.
- Cross-attribution check: `backend_hub.feature_ids()` = 421 and equals the attribution key set;
  for all 421 IDs `attribution[id] == hub.FEATURE_TO_MODULE[id]` (0 mismatches); each attributed ID
  appears in its owning module's `backend-module-id-coverage.json` per-module list (0 exceptions).
- `backend-module-id-coverage.json.per_module` union = 477 unique IDs; `combined` = the same 477.
  The 56 IDs in that union but **not** attributed are cross-module/prose references, including
  `W1.18`, `Y6.4`, `C11.1`. The final attribution correctly excludes all of them: `attribution - union = []`.
  This confirms "no false cross-attribution" and ACCOUNTING §1's "477 combined is not the denominator".
- `missing_not_started` = exactly the seven D6 IDs above, all `not_started`/`local_module`.

### 3.3 `scripts/verify_backend_operation.py --strict` — CONFIRMED, with documentation defect (C4)

Code inspection:

- The evidence-gate loop `for fid, mod in attribution.items()` (line 399) iterates **all 421** IDs and
  checks module AST construct (or evidence-doc cross-check), test reference (or cross-check), non-empty
  `acceptance_criteria`, and evidence-doc existence + ID mention (lines 418-441).
- Hard checks (lines 51-126) also enforce 865 rows, parity equality, no duplicate IDs, 854/9/2 status
  counts, 421 attribution, path/evidence existence, 20 modules, hub/capability registration.
- `strict = "--strict" in sys.argv` (line 452); `if strict and gate_failures: errors.append(...)` (467-469);
  `if errors: ... raise SystemExit(1)` (470-474). Non-strict runs report but exit 0.

Live probe on a **temporary copy** (no tracked source modified): full copy of the worktree made with
`robocopy ... /XD .git` into `C:\Users\Admin\AppData\Local\Temp\opencode\probe_root`; script run there.

| Run | Result | Exit |
| :- | :- | :-: |
| Baseline, no flag | `attributed IDs audited: 421`, `passing all checks: 421`, `failing: 0`, `BACKEND OPERATION VERIFICATION OK` | 0 |
| One evidence row removed from temp copy of `master-plan-v6-d3-backend-evidence.md`, no flag | `passing 420`, `failing 1` (`D3.10 ... evidence doc does not mention ID`), still `VERIFICATION OK` | 0 |
| Same perturbed copy, `--strict` | `EVIDENCE-BASED GATE (ENFORCED)`, `1 attributed IDs fail the evidence gate`, `VERIFICATION FAILED` | **1** |

Conclusion: `--strict` truly enforces all 421 gate checks and exits non-zero on any failure, as claimed
in ACCOUNTING FINAL AMENDMENT (line 141), MATRIX FINAL AMENDMENT (line 139), FINAL L250, and BACKLOG L36.
The only defect is the contradicting docstring/error text recorded as C4.

### 3.4 Gate claims in FINAL-ENGINEERING-REPORT.md and accounting docs — CONFIRMED where testable

| Claim | Location | Result |
| :- | :- | :- |
| 865 rows / 854 verified / 9 not_started / 2 blocked; SHA-256 as quoted | FINAL L181-184, ACCOUNTING L5-7, MATRIX L3-4 | Confirmed (§3.1) |
| Parity identical | FINAL L72, TASKBOARD L26 | Confirmed (§3.1) |
| 421 deduplicated backend denominator; per-module sum 421; 477 combined not used | ACCOUNTING L25-31, FINAL L189 | Confirmed (§3.2) |
| 20 genuine modules, 421 hub features, 4 backend capabilities | FINAL L80-86, TASKBOARD L17-19 | Confirmed: `hub.modules()`=20, `feature_ids()`=421, capabilities `backend.modules/.describe/.invoke/.verify` registered |
| `verify_v6_audit.py` CONSISTENCY OK (865) | FINAL L249, TASKBOARD L26 | Confirmed, exit 0 |
| Dependency graph FRESH; license gate OK; 8 workflow YAMLs parse; SHA-pinned `uses:` | FINAL L251, TASKBOARD L26 | Confirmed (§3.1) |
| `verify_backend_operation.py --strict` OK, 421/421, non-zero on failure | FINAL L250, ACCOUNTING L140-141, MATRIX L138-139, BACKLOG L36 | Confirmed by code + probe (§3.3) |
| Production release BLOCKED (signing, clean-VM, push authorization, owner gates) | FINAL L46/L116/L173, ACCOUNTING L110 | Consistent with documented external gates; no status changed |

The contradictions that remain are C1-C5 in §1; all other numeric/gate claims in the listed files
reconcile with the code and artifacts.

---

## 4. Conclusion

The quantitative core of the promotion candidate is sound: **865** canonical IDs unchanged
(**854 verified / 9 not_started / 2 blocked**), `parity.json` byte-identical, **421** uniquely and
correctly attributed backend IDs with no duplicates or false cross-attribution, and a `--strict` gate
that audits all 421 IDs and exits non-zero on failure. The items requiring lead attention are
documentation-level: the W1.18/Y6.4 ownership mislabel (C1), the candidate manifest's dual
classification of `Cargo.toml` (C2), stale 361/60 figures left in "current" sections (C3), the verifier
docstring's denial of strict enforcement (C4), and the composite report's competing "definitive"
test-suite figures (C5). No canonical status or owner decision was altered by this audit.
