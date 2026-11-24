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
5. **Traceability cross-check (follow-up).** Lead investigation showed that
   e.g. `Y5.7` is implemented and tested (`test_y5_7_status_and_gateway_commands`)
   and its evidence doc has a row mapping `Y5.7 -> channel_status,
   gateway_start -> test_y5_7_status_and_gateway_commands`; the ID appears in
   the module only in prose. The verifier now accepts an alternative evidence
   path: a per-ID evidence-table row that names a real symbol and a real test
   function (Section 3, path (b)). This recovered 130 IDs without changing any
   status.
6. **This document** — records the defect, the changes, the exact checks, the
   measured results, and the limitation.

Invariants preserved: 865 total features; `priority` and `original_priority`
unchanged for every row; status counts remain
`{verified: 854, not_started: 9, blocked: 2}`; no status downgrades.

## 3. Exact strengthened checks

For each of the 421 IDs in `backend-final-attribution.json`, the verifier now
audits the registry row against real artifacts. All parsing is `ast`-based;
unparseable files are a hard failure of the relevant check.

An ID passes checks 1 and 2 via **either** path (a) **or** path (b):

- **Path (a) — direct AST evidence.** The module/test artifacts themselves
  carry the ID or a mapped symbol.
- **Path (b) — evidence-table cross-check.** The evidence document's per-ID
  Markdown table row names a concrete symbol and a concrete test function, and
  both are then verified to exist as real AST definitions. This closes the
  traceability convention gap where an ID is implemented and tested but the
  module mentions the ID only in a comment/docstring.

1. **Module — real code construct (AST, path (a)).** The source file must
   exist and contain at least one of:
   - a string-literal **dict key** equal to the ID;
   - membership of the ID as a string element of a module-level **declared
     collection** (list / tuple / set, e.g. `FEATURE_IDS`);
   - a **function / class / assignment name** equal to the ID.
   Comments and plain strings (module/function docstrings, message strings,
   dict *values*) are explicitly excluded and still never pass path (a).
2. **Test — AST reference (path (a)).** The test file must exist and a test
   function/class/decorator must reference either the literal ID (exact string
   constant, or normalized token such as `E7.29` -> test class `E729_*`) or a
   **symbol mapped to the ID** by the module's declared registries. Mapped
   symbols are derived from module-level dict values, collection membership
   (the registry name itself), and the module docstring's
   `ID :class:`Foo` / :func:`bar`` lines. This deliberately accepts tests that
   reference symbols by name rather than by a copied ID string — the red team
   classified those as benign.
3. **Path (b) — per-ID evidence row cross-check.** Markdown tables are parsed
   generically: a header row followed by a separator, then rows whose first
   cell is the ID. Backtick-quoted identifiers are extracted from the symbol
   and test columns (located by header keywords such as `symbol`, `contract`,
   `entry point`, `implemented`, `surface`, `behaviour`, `test`; if a header
   has no such column, all data cells are used). Acceptance requires **both**:
   - at least one named symbol that is a real **function / class / method /
     assignment** in the registry's source module (AST: `FunctionDef`,
     `AsyncFunctionDef`, `ClassDef`, assignment targets including attributes);
   - at least one named test function that is a real `test*` function in the
     registry's test file (AST), including `test_*` wildcard prefixes from
     rows such as `` `test_y101_*` (6) ``, resolved by real-name prefix match.
   A valid path (b) result satisfies both check 1 and check 2. A row that names
   only symbols (e.g. the D6/E5 tables, whose test column is a bare count or a
   status word) does **not** pass.
4. **Acceptance criteria** — `acceptance_criteria` must be non-empty.
5. **Evidence doc** — the file named by `verification_evidence` must exist
   **and** contain the literal ID (a path (b) row necessarily mentions it).

The verifier caches module/test analysis per path, prints a per-ID failure
line with reasons, and summarizes counts per check. The original hard checks
(865 rows, parity equality, 421 attribution, path/doc existence, 20 modules,
4 capabilities, hub index, imports, operation documents) are unchanged and
still fail the script if broken.

## 4. Results of the gate after the traceability cross-check (run of this branch)

Before the cross-check: 231 passed / 190 failed. After adding path (b):

```
attributed IDs audited: 421
passing all checks: 361
failing at least one check: 60
   33 x module: no AST construct for ID and no evidence-doc row mapping the ID to a real symbol + real test
   28 x evidence doc does not mention ID
    1 x test: no test function/class/decorator references the ID or a mapped symbol,
             and no evidence-doc row names a real test function
    0 x acceptance_criteria empty   (remediated: 93 -> 0)
```

62 check-failures across 60 IDs (`Y3.8` fails three checks; the other 59 IDs
fail one each). 130 previously failing IDs were recovered by the cross-check.
By module, the 60 failing IDs:

| Module | Failing IDs |
|---|---|
| d6_reliability_backend | 18 |
| e6_x5_x6_backend | 27 |
| e5_backend | 13 |
| y2_backend | 1 |
| w7_x1_y5_d1_backend | 1 |

Full remaining failure list, exactly as printed by the verifier:

<details>
<summary>All 60 remaining failures with reasons</summary>

```
D6.1, D6.10, D6.11, D6.12, D6.13, D6.15, D6.16, D6.19, D6.22, D6.24,
D6.25, D6.3, D6.4, D6.5, D6.6, D6.7, D6.8, D6.9  [d6_reliability_backend]
  -> module: no AST construct and no valid evidence-doc row
E5.10, E5.11, E5.13, E5.16, E5.17, E5.18, E5.19, E5.2, E5.3, E5.5,
E5.6, E5.7, E5.8  [e5_backend]
  -> module: no AST construct and no valid evidence-doc row
E6.11, E6.12, E6.13, E6.14, E6.2, E6.3, E6.4, E6.6, E6.7,
X5.10, X5.11, X5.12, X5.13, X5.2, X5.3, X5.4, X5.7, X5.8,
X6.1, X6.10, X6.2, X6.3, X6.4, X6.5, X6.6, X6.8, X6.9  [e6_x5_x6_backend]
  -> evidence doc does not mention ID
Y2.16  [y2_backend]
  -> module: no AST construct and no valid evidence-doc row
Y3.8   [w7_x1_y5_d1_backend]
  -> module: no AST construct and no valid evidence-doc row;
     test: no ID/mapped-symbol reference and no evidence-doc row naming a real test;
     evidence doc does not mention ID
```

</details>

### Interpretation

- The 33 module failures are IDs whose module mentions the ID only in prose
  *and* whose evidence row does not name a concrete test function (e.g. D6 rows
  have a bare count `3` in the test column; E5 rows have a status word and no
  test column). This is a documentation/traceability gap, not proof the
  behavior is absent.
- The 28 evidence-doc failures are module-level summary docs (E6/X5/X6) that
  never enumerate the individual ID and therefore have no per-ID row to
  cross-check.
- `Y3.8` is referenced inside another module's evidence doc (as part of a
  W7/X1/Y5/D1 scope) but has no row of its own; its test also does not name the
  ID or a mapped symbol.
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
- The path (b) cross-check trusts the evidence row's *claim* that a symbol and
  a test belong to the ID. It verifies that both names resolve to real AST
  definitions, but it does **not** prove the named test actually exercises the
  named symbol, that the symbol implements the feature's full acceptance
  criterion, or that the row was independently reviewed. `test_*` wildcard
  rows are accepted by real-name prefix match, which is a convention, not a
  behavioral guarantee. The evidence docs were authored by the implementation
  agents, so the cross-check remains within the same certification layer.
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
`BACKEND OPERATION VERIFICATION OK` while printing the 60-ID reported-only
failure list above. Regeneration was deterministic: `PLAN-INDEX.json` and
`parity.json` remain byte-identical to each other (SHA-256 prefix
`62fd5c6ac2d166e8` before and after), and `Keel_Master_Plan_v6.md` was unchanged
(`312d61782dd19a94`). `python -c "import ast;ast.parse(open(...).read())"` on
`scripts/verify_backend_operation.py` succeeded.


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
