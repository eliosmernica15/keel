# Backend completion accounting — authoritative deduplicated denominator

**Status:** normative accounting for the v6 backend workstream. Supersedes ad-hoc
"backend percentage" statements elsewhere; does not change any registry status.
**Source of truth:** `PLAN-INDEX.json`, SHA-256
`62fd5c6ac2d166e8cb1f5752c168d22d56d767c7e6a5bf9384696756a4a5b2f6` (865 rows:
854 `verified`, 9 `not_started`, 2 `blocked`).
**Corroborating artifacts:** `backend-final-attribution.json` (421 unique ID → module
mappings), `backend-module-id-coverage.json` (per-module coverage; 7 `not_started` IDs
listed as `missing_not_started`), `BACKEND-IMPLEMENTATION-DETAIL.md` (20 modules),
`REGISTRY-EVIDENCE-INTEGRITY.md` (421/421 final traceability result),
`AUDIT-REMEDIATION-SUMMARY.md` (audit verdicts).

## 1. Why a deduplicated denominator is required

Three numbers are often conflated:

- **865** — the canonical plan registry (authoritative total; one row per plan ID).
- **228** — the historical v5 base registry (addenda 1–2). It is a **subset** of 865, not
  an additional set.
- **398** — `feature-checklist.md` observable contracts (a cross-cutting clean-room
  *observability* inventory with IDs `S1-CLI-001` … `S15-WORK-012`). It is **not
  additive** to either registry; see §5 and `REMAINING-WORK-MATRIX.md`.

The 20 backend modules declare 421 features in total. The sum of the per-module feature
counts in `BACKEND-IMPLEMENTATION-DETAIL.md` is exactly **421**, and
`backend-final-attribution.json` contains exactly **421 unique IDs** — i.e. the module
declarations are already deduplicated (no ID is attributed to two modules). This is the
authoritative backend denominator. The larger `backend-module-id-coverage.json`
`combined` list (477 IDs) includes cross-module references and is **not** used as the
denominator.

## 2. Classification of the 865 registry rows (mutually exclusive)

| Class | Rows | Status / basis |
| :- | :-: | :- |
| Backend-attributed, verified (dedup denominator) | 421 | `verified`; 20 modules, 421 unique IDs |
| Verified, applicable, not backend-attributed | 426 | `verified`; product/contract/operational rows |
| Owner-gated (excluded) | 3 | C11.1 + C11.2 (`blocked`, tier `owner_gated`); C11.5 (`verified`, `owner_approval_required=true`) |
| External dependency (excluded) | 3 | B4.8, B6.6, C11.8 (`verified`, tier `external_dependency`) |
| Dormant / descriptor-only (excluded) | 3 | B6.2, B6.3, B6.5 (`verified`, tier `descriptor`) |
| In-scope `not_started` | 9 | 7 D6 builder conventions + W1.18 + Y6.4 |
| **Total** | **865** | |

Reconciliation checks:
- Verified rows: 421 + 426 + 7 (the three excluded classes contain 7 verified rows) = **854**.
- Blocked rows: C11.1 + C11.2 = **2** (already counted in the owner-gated class, not double counted).
- Not-started rows: **9** (W1.18 and Y6.4 are local_module/operational, not owner-gated or external;
  the 7 D6 rows are builder-convention rules, not backend code).
- Excluded rows: 3 + 3 + 3 = **9**. None of the 9 appears in the 421 backend-attributed set.
- Class sum: 421 + 426 + 3 + 3 + 3 + 9 = **865**. ✔

## 3. Completion percentages (computed, not inflated)

Let `B = 421` (deduplicated backend-attributed requirements), `V_B = 421` (of those
`verified`), `T_B = 421` (pass the strengthened traceability gate), `L_B = 0` (verified
with certification limitation). `T_B + L_B = V_B = 421`.

**Formula 1 — backend requirement completion, registry-status sense:**

```
completion_backend_status = V_B / B = 421 / 421 = 1.000 = 100.0%
```

Read this narrowly: *every deduplicated backend-attributed ID carries a `verified`
registry status.* It is **not** a claim of production readiness, native verification, or
full traceability.

**Formula 2 — backend completion, certification-qualified (the number to quote for
traceability):**

```
completion_backend_certified = T_B / B = 421 / 421 = 1.00000 = 100.0%
limitation_rate             = L_B / B =   0 / 421 = 0.00000 = 0.0%
```

The 60 rows formerly listed as limited in `REMAINING-WORK-MATRIX.md` §5 are now fully traceable (historical list only). They remain `verified`;
the gap is in the evidence/certification layer (prose-only ID mentions, module-level
evidence docs without per-ID rows), not in the implementation status.

**Formula 3 — applicable registry-wide completion (context, not the backend figure):**

```
applicable_denominator = 865 - (3 owner-gated + 3 external + 3 dormant) = 856
verified_applicable    = 854 - 7 verified-excluded = 847
completion_applicable  = 847 / 856 = 0.98949 = 99.0%   (9 not_started remain = 1.1%)
```

**Formula 4 — raw registry status (least informative; includes the 7 verified excluded
rows):**

```
completion_registry_raw = 854 / 865 = 0.98728 = 98.7%
```

## 4. Scope boundary — what is deliberately *not* counted as backend incomplete

- The **7 D6 rows** are human-workflow/builder-convention rules (Review, Convention,
  Doc-sync gate, Builder rule, Template, Doc). They appear in
  `backend-module-id-coverage.json` `missing_not_started` but not in the 421 attribution,
  because they are process conventions rather than backend code contracts. They are
  reported as in-scope `not_started` in §2, not hidden.
- **W1.18** (license/notices verification) and **Y6.4** (repo visibility observation,
  gated by G1) are licensing/external-observation tasks, not backend code.
- **C11.1 / C11.2** are owner-gated `blocked` rows; they are excluded from the applicable
  backend denominator and remain visible in `REMAINING-WORK-MATRIX.md` §4.
- The **60 certification-limited rows** are not reclassified and do not reduce
  `completion_backend_status`; they reduce `completion_backend_certified` only.
- Audit-accepted external gates (native Linux/macOS sandbox verification, provider
  credentials, signing, clean-VM, push authorization) are outside local backend scope.

## 5. Cross-inventory note (non-additive)

`feature-checklist.md` declares **398** observable contracts (15 subsystems, S1–S15);
the rendered tables currently contain **410 unique** contract IDs — a pre-existing
internal discrepancy in that document, reported transparently here. Matching its
behaviour descriptions to verified PLAN-INDEX rows is a *lexical correspondence proxy*,
not authoritative traceability: a reproducible rare-bigram matcher (content words ≥4
chars, stoplist removed; ≥1 shared bigram with document frequency ≤6 across the verified
corpus) returns **180 / 410 (43.9%)** matches against all 854 verified rows and
**119 / 410 (29.0%)** against the 421 backend-attributed rows. Stricter thresholds
collapse the result to 5 / 410, so no exact cross-inventory count is asserted. These
contracts are a different, cross-cutting observability inventory and must **never** be
added to 865, 421 or 228.

## 6. One-line authoritative statement

> Backend denominator = **421** deduplicated, backend-attributed registry IDs (from the
> 865-row canonical registry). **421 / 421 = 100.0%** carry `verified` status;
> **421 / 421 = 100.0%** are fully traceable and **0 / 421 = 0.0%** are verified with a
> certification limitation. Nine registry rows remain `not_started` and two `blocked`;
> nine rows are excluded as owner-gated/external/dormant. No figure here is a production
> readiness claim.


## FINAL AMENDMENT — all 421 traceability gaps closed (authoritative)

A later remediation batch (`agent/final-trace`, merged and pushed) added AST-visible
`FEATURE_TRACEABILITY` declarations and per-ID evidence rows to every owning module.
`python scripts/verify_backend_operation.py` now reports **421 passing / 0 failing**,
and `--strict` enforces the gate with a non-zero exit on any failure.

All earlier figures of **361 / 421 traceable** and **60 failing IDs** in this document
are **historical** — they describe the state before that batch and are retained only
for provenance. Current authoritative certification:

- Fully traceable: **421 / 421 = 100.0%**
- Verified-with-limitation: **0 / 421 = 0.0%**
- Registry unchanged: 865 rows, 854 verified / 9 not_started / 2 blocked.

The gate remains a certification layer over tests and declarations; it does not claim
native cross-platform or live-provider verification.
