# Registry evidence integrity — remediation of the red-team HIGH finding

Branch: `agent/auditfix-docs`.
Evidence: `AUDIT-REDTEAM.md`, Finding 1 (commit `afcda88`, worktree `audit9/redteam`).
Scope: registry certification integrity only. No status changes, no new deps, no
frontend, no push.

## 1. What was wrong

The headline claim "421 newly verified IDs" was a bookkeeping artifact, not a
behavioral verification result:

- `keel/scripts/build_plan_index.py` marked a feature `verified` purely by
  dictionary membership: `verified = fid in implemented_ids or backend_evidence
  is not None`. The same `BACKEND_EVIDENCE` dict supplied the only source path,
  the only test path, and the evidence-document filename.
- The comment immediately above that logic said *"never claim verification just
  because a source or test file path happens to be mentioned"* and then did
  exactly that. (The comment has been corrected.)
- `scripts/verify_backend_operation.py` checked only that the paths/doc exist
  and that `verification_evidence` was a non-empty string. It never opened a
  test, never parsed a module, and never read an acceptance criterion.
- **93 of the 421 attributed IDs were `verified` with an empty
  `acceptance_criteria` list** — nothing to satisfy. Across the whole 865-row
  registry, 117 rows had empty criteria (24 of them un-attributed and left
  untouched, as they are outside this remediation's scope).
- For all 421, `verification_evidence` was just an `.md` filename, and a
  module-level evidence doc often does not mention the individual ID at all.

The red team also established that the modules themselves are genuine
implementations. The overclaim was at the certification and integration layers;
this remediation addresses the certification layer only.

## 2. What changed

1. **`keel/scripts/build_plan_index.py`** — added
   `_derived_backend_acceptance_criteria()`. For any attributed ID whose source
   extraction supplied no criteria, it now emits four criteria that are
   explicitly labelled `[DERIVED - source omitted acceptance criteria]` and are
   built from that ID's own feature text plus its hardcoded
   module / source path / test path / evidence doc. These are reconciliation
   criteria, **not** invented source requirements; every entry states that it
   was derived because the source omitted criteria. The self-contradictory
   comment was rewritten to describe attribution honestly.
2. **`PLAN-INDEX.json` and `parity.json`** — regenerated with the generator
   (never hand-edited). Exactly 93 rows changed, and the only field that
   changed in those rows is `acceptance_criteria`.
3. **`Keel_Master_Plan_v6.md`** — regenerated with `build_v6_plan.py` (byte
   identical: the master-plan renderer does not project acceptance criteria).
4. **`scripts/verify_backend_operation.py`** — strengthened with an AST-based,
   evidence-based per-ID gate (Section 3). The gate is **reported, not
   enforced**: it prints a per-ID failure list and totals but does not alter
   any status and does not fail the script. The lead decides remediation.
5. **This document** — records the defect, the change, the exact checks, the
   measured results, and the limitation.

Invariants preserved: 865 total features; `priority` and `original_priority`
unchanged for every row; status counts remain
`{verified: 854, not_started: 9, blocked: 2}`; no status downgrades.

## 3. Exact strengthened checks

For each of the 421 IDs in `backend-final-attribution.json`, the verifier now
audits the registry row against real artifacts. All parsing is `ast`-based;
unparseable files are a hard failure of the relevant check.

1. **Module — real code construct (AST).** The source file must exist and
   contain at least one of:
   - a string-literal **dict key** equal to the ID;
   - membership of the ID as a string element of a module-level **declared
     collection** (list / tuple / set, e.g. `FEATURE_IDS`);
   - a **function / class / assignment name** equal to the ID.
   Comments and plain strings (module/function docstrings, message strings,
   dict *values*) are explicitly excluded. A module that mentions the ID only
   in prose fails this check.
2. **Test — AST reference.** The test file must exist and a test
   function/class/decorator must reference either the literal ID (exact string
   constant, or normalized token such as `E7.29` -> test class `E729_*`) or a
   **symbol mapped to the ID** by the module's declared registries. Mapped
   symbols are derived from module-level dict values, collection membership
   (the registry name itself), and the module docstring's
   `ID :class:`Foo` / :func:`bar`` lines. This deliberately accepts tests that
   reference symbols by name rather than by a copied ID string — the red team
   classified those as benign.
3. **Acceptance criteria** — `acceptance_criteria` must be non-empty.
4. **Evidence doc** — the file named by `verification_evidence` must exist
   **and** contain the literal ID.

The verifier caches module/test analysis per path, prints a per-ID failure
line with reasons, and summarizes counts per check. The original hard checks
(865 rows, parity equality, 421 attribution, path/doc existence, 20 modules,
4 capabilities, hub index, imports, operation documents) are unchanged and
still fail the script if broken.

## 4. Results of the new gate (run of this branch)

```
attributed IDs audited: 421
passing all checks: 231
failing at least one check: 190
  163 x module: no AST construct for ID (ID appears only in comments/docstrings/plain strings)
   28 x evidence doc does not mention ID
    8 x test: no test function/class/decorator references the ID or a mapped symbol
    0 x acceptance_criteria empty   (remediated: 93 -> 0)
```

199 check-failures across 190 IDs (8 IDs have two reasons, 1 has three).
By module, the 190 failing IDs:

| Module | Failing IDs |
|---|---|
| w7_x1_y5_d1_backend | 32 |
| e6_x5_x6_backend | 27 |
| y1_config_backend | 25 |
| d6_reliability_backend | 18 |
| x2_orchestration_backend | 16 |
| x3_memory_backend | 16 |
| x8_backend | 15 |
| y2_backend | 15 |
| e5_backend | 13 |
| y3_backend | 13 |

Full per-ID lists by failing check (an ID may appear in more than one list):

<details>
<summary>Module-construct failures (163)</summary>

D1.11, D1.2, D1.3, D1.6, D1.7, D1.8, D1.9, D6.1, D6.10, D6.11, D6.12,
D6.13, D6.15, D6.16, D6.19, D6.22, D6.24, D6.25, D6.3, D6.4, D6.5, D6.6,
D6.7, D6.8, D6.9, E5.10, E5.11, E5.13, E5.16, E5.17, E5.18, E5.19, E5.2,
E5.3, E5.5, E5.6, E5.7, E5.8, W7.11, W7.12, W7.15, W7.18, W7.2, W7.20,
W7.7, W7.9, X1.10, X1.11, X1.12, X1.14, X1.15, X1.16, X1.6, X1.9, X2.1,
X2.10, X2.11, X2.12, X2.13, X2.14, X2.15, X2.16, X2.2, X2.3, X2.4, X2.5,
X2.6, X2.7, X2.8, X2.9, X3.1, X3.10, X3.11, X3.12, X3.13, X3.14, X3.15,
X3.16, X3.2, X3.3, X3.4, X3.5, X3.6, X3.7, X3.8, X3.9, X8.10, X8.11,
X8.12, X8.13, X8.14, X8.15, X8.16, X8.17, X8.3, X8.4, X8.5, X8.6, X8.7,
X8.8, X8.9, Y1.1, Y1.10, Y1.11, Y1.12, Y1.13, Y1.14, Y1.15, Y1.18, Y1.21,
Y1.22, Y1.23, Y1.25, Y1.26, Y1.27, Y1.28, Y1.29, Y1.31, Y1.32, Y1.33,
Y1.34, Y1.35, Y1.36, Y1.37, Y1.38, Y1.39, Y2.10, Y2.11, Y2.12, Y2.13,
Y2.15, Y2.16, Y2.17, Y2.18, Y2.19, Y2.21, Y2.22, Y2.23, Y2.24, Y2.25,
Y2.9, Y3.1, Y3.12, Y3.14, Y3.15, Y3.16, Y3.17, Y3.18, Y3.19, Y3.20,
Y3.21, Y3.3, Y3.5, Y3.7, Y3.8, Y5.1, Y5.2, Y5.3, Y5.5, Y5.6, Y5.7,
Y5.8, Y5.9

</details>

<details>
<summary>Test-reference failures (8)</summary>

Y1.11, Y1.15, Y1.21, Y1.26, Y1.27, Y1.32, Y1.38, Y3.8

</details>

<details>
<summary>Evidence-doc-mention failures (28)</summary>

E6.11, E6.12, E6.13, E6.14, E6.2, E6.3, E6.4, E6.6, E6.7, X5.10, X5.11,
X5.12, X5.13, X5.2, X5.3, X5.4, X5.7, X5.8, X6.1, X6.10, X6.2, X6.3,
X6.4, X6.5, X6.6, X6.8, X6.9, Y3.8

</details>

### Interpretation

- The 163 module failures are IDs whose implementing module mentions the ID
  only in docstrings/comments/string constants while the feature logic exists
  under a real symbol. They are evidence-linkage gaps, not proof the behavior
  is absent; they mirror the red team's point that a source-text regex would
  have accepted them.
- The 28 evidence-doc failures are module-level summary docs that never
  enumerate the individual ID.
- The 8 test failures are IDs whose tests exercise behavior without naming the
  ID or a mapped symbol in a test function/class/decorator.
- These are reported for the lead. **No status was changed** as a result of
  this gate.

## 5. Honest limitation

The derived criteria and the strengthened verifier improve the *certification*
of the registry; they do not turn it into native or production verification.
This remains a **generator-driven certification layer over unit tests**:

- The derived criteria were written by this remediation from existing feature
  text and hardcoded attribution; they were not present in the source plan and
  are labelled as derived for exactly that reason.
- The verifier checks that code constructs, tests, criteria and evidence docs
  exist and are linked. It does **not** execute each feature's behavioral test
  per ID, does not exercise the capability hub end-to-end for each ID, and does
  not prove the feature is reachable from production workflows.
- The red team's other findings — thin integration façade (F2), source-text
  `backend.verify` (F3), uncallable advertised x3 dispatch functions (F4), and
  the descriptor-only E7.41 storage seam (F5) — are outside this certification
  remediation and are neither fixed nor rebutted here.
- Consequently "verified" in `PLAN-INDEX.json` should continue to be read as
  "certified by the project's own generators and unit-test evidence," not as a
  claim of native/production behavior.

## 6. Verification run

Command (all four must pass):

```
python keel/scripts/build_plan_index.py && python keel/scripts/build_v6_plan.py \
  && python scripts/verify_v6_audit.py && python scripts/verify_backend_operation.py
```

Result on this branch: all four exited 0. `verify_v6_audit.py` reported
`CONSISTENCY OK` (865 registry rows). `verify_backend_operation.py` reported
`BACKEND OPERATION VERIFICATION OK` while printing the 190-ID reported-only
failure list above. Regeneration was deterministic: `PLAN-INDEX.json` and
`parity.json` remain byte-identical to each other; `Keel_Master_Plan_v6.md`
was unchanged by regeneration.
