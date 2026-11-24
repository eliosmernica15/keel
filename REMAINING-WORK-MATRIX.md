# Remaining work matrix — current authoritative state

> **Source of truth:** `PLAN-INDEX.json` (865-row canonical registry), SHA-256
> `62fd5c6ac2d166e8cb1f5752c168d22d56d767c7e6a5bf9384696756a4a5b2f6`.
> Status counts were read directly from that file; **no status has been changed by this
> document**. This matrix supersedes an earlier snapshot, retained only as provenance in §8.
>
> Companion authoritative documents: `BACKEND-COMPLETION-ACCOUNTING.md` (deduplicated
> backend denominator), `REGISTRY-EVIDENCE-INTEGRITY.md` (the 60 certification gaps),
> `AUDIT-REMEDIATION-SUMMARY.md` (audit verdicts and accepted limitations).

## 1. Honesty note — read first

`not_started` is an honest status and **must not be marked `verified` without real
evidence**: a shipped implementation in the referenced source files, passing automated
tests, and behaviour checked in the real application/runtime where applicable. A plan
row, a design note, a generated stub, a green unit test alone, or an owner decision does
not promote a row. Rows marked `blocked` need a named external dependency or owner
decision resolved first.

`verified` in this registry continues to mean **certified by the project's own
generators and unit-test evidence**, not proven native/production behaviour. Sixty
verified rows carry a *certification limitation* (§5); that is a limitation of the
evidence layer, not a status change.

## 2. Status totals (normative)

| Status | Rows | Share of 865 |
| :- | :-: | :-: |
| verified | 854 | 98.7% |
| not_started | 9 | 1.0% |
| blocked | 2 | 0.2% |
| **Total** | **865** | **100%** |

Priority distribution in the registry is unchanged: P0 240 / P1 524 / P2 101.
`original_priority` preserves the pre-X0.1 re-ranking value. All 854 verified rows have
non-empty `source_files`, `test_references` and `verification_evidence`.

## 3. The 9 `not_started` rows — exact registry reasons

All nine are honest human-workflow / licensing / external-observation rows. Seven are
builder-constitution conventions from Addendum 6 §7; none has a source file, test or
implementation artifact in its registry row.

| ID | Feature (registry `feature`) | Source | Pri | MS | Registry `detail` (stated reason) | Why still `not_started` |
| :- | :- | :- | :- | :- | :- | :- |
| D6.14 | Tests describe behavior, not "correctness"; change obsolete behavior together with its tests and explain why. | Add.6 | P1 | M0 | `Review` | Builder-constitution review convention (Add.6 §7). No source file, test reference or evidence string; adoption is a process/review decision, not a code change. |
| D6.17 | Agent Notes (ADR-like) only for durable decision rationale; archived notes frozen, never edited or treated as current authority. | Add.6 | P1 | M0 | `Convention` | Builder-convention rule. No implementation artifact; remains a documentation-policy decision for the builder. |
| D6.18 | Prefer maintained dependencies over hand-rolling when they delete owned code and tests. | Add.6 | P1 | M0 | `Review` | Builder review rule. No implementation artifact; enforced only by review practice, which is not registered evidence. |
| D6.2 | Plugins, not loop changes: new behavior attaches to documented extension points; changing the loop requires updating the architecture doc. | Add.6 | P1 | M0 | `Doc-sync gate` | Process/doc-sync gate. No source file or test; the gate is a convention, not a shipped check. |
| D6.20 | Run only relevant checks locally: match evidence to the change (focused tests, snapshots, doc-sync, built smokes, real-provider e2e); CI owns exhaustive coverage; don't repeat a passing check for commit/push. | Add.6 | P1 | M0 | `Builder rule` | Builder rule. No implementation artifact; not an executable contract in the registry. |
| D6.21 | PR hygiene: one `kind/*` and all material `area/*` labels; rewrites use force-with-lease only; PR description template. | Add.6 | P1 | M0 | `Template` | Repository-process template. No source file or test; requires owner/builder adoption of the PR template. |
| D6.23 | Defensive-patterns doc read before touching package surfaces, remote services, client state, conversation/session behavior, lifecycle/concurrency/subprocess/teardown code. | Add.6 | P1 | M0 | `Doc` | Required-reading documentation convention. No implementation artifact. |
| W1.18 | MIT license + `THIRD_PARTY_NOTICES.md`. | Add.5 | P0 | M0 | `Same notices rule; verify LICENSE text and every vendor/ license in M0 before reading any code.` | Licensing/notices verification task. No source file or test in the row; needs the actual LICENSE and every vendored license text checked and recorded before promotion. |
| Y6.4 | repo visibility: Public, 0 stars/forks | Add.4 | P0 | M1 | `Repo is **Public** with 0 stars/forks (as of this fetch).` Depends on `G1`. | External repository observation, not a code change: describes the source repo's visibility/star state at fetch time; depends on gate `G1` and must not be promoted from a local implementation. |

## 4. The 2 `blocked` rows — owner / external gates

| ID | Feature | Source | Pri | MS | Exact reason and unblock action |
| :- | :- | :- | :- | :- | :- |
| C11.1 | Source-hosting caveats to decide (verify current terms): on GitHub's free plan, private repos may lack branch protection and advanced code/secret scanning; GitHub Pages for private repos may need a paid plan. Options: accept and use local pre-push hooks + gitleaks + signed commits; host the primary private repo on a free forge with protected branches (e.g. GitLab free tier or self-hosted Forgejo/Gitea) and mirror to GitHub; or consciously pay later (gate G6). | Add.2 | P0 | M1 | `owner_approval_required=true`, tier `owner_gated`. Owner decision on source hosting (gate **G6**). The final report records the decision as made (private repo confirmed), but the registry still holds `blocked`; update the registry only after owner sign-off and a recorded verdict. |
| C11.2 | Security hygiene for the private repo: mandatory 2FA, signed commits, least-privilege tokens, Actions pinned by commit SHA, restricted Actions on forks (forks disabled), environment secrets with required reviewer for release publishing, access review checklist. | Add.2 | P0 | M1 | `owner_approval_required=true`, tier `owner_gated`. GitHub Free private plan: branch protection `403`, signed commits `404` / no GPG key, fork restriction `422` (org-owned only). Unblock by plan upgrade, alternate forge, or a documented compensating-control exception; 2FA is owner-account level. |

## 5. 60 traceability gaps — `verified with certification limitation` (no status change)

The strengthened registry gate (`scripts/verify_backend_operation.py`, documented in
`REGISTRY-EVIDENCE-INTEGRITY.md` §3–§4) cross-checks the 421 backend-attributed IDs
against real AST constructs, real test functions, non-empty acceptance criteria and
evidence documents. Result: **361 pass, 60 fail at least one check**.

These 60 rows **remain `verified`** in `PLAN-INDEX.json`. The failures are certification
and traceability-convention gaps — a module mentions an ID only in prose, or a
module-level evidence doc never enumerates the individual ID — not proof the behaviour
is absent. Their honest classification is **verified with certification limitation**.

| Module | Failing IDs | Count |
| :- | :- | :-: |
| `d6_reliability_backend` | D6.1, D6.10, D6.11, D6.12, D6.13, D6.15, D6.16, D6.19, D6.22, D6.24, D6.25, D6.3, D6.4, D6.5, D6.6, D6.7, D6.8, D6.9 | 18 |
| `e5_backend` | E5.10, E5.11, E5.13, E5.16, E5.17, E5.18, E5.19, E5.2, E5.3, E5.5, E5.6, E5.7, E5.8 | 13 |
| `e6_x5_x6_backend` | E6.11, E6.12, E6.13, E6.14, E6.2, E6.3, E6.4, E6.6, E6.7, X5.10, X5.11, X5.12, X5.13, X5.2, X5.3, X5.4, X5.7, X5.8, X6.1, X6.10, X6.2, X6.3, X6.4, X6.5, X6.6, X6.8, X6.9 | 27 |
| `y2_backend` | Y2.16 | 1 |
| `w7_x1_y5_d1_backend` | Y3.8 | 1 |
| **Total** | | **60** |

Failure breakdown: 33 × no AST construct / no valid evidence-doc row; 28 × evidence doc
does not mention the ID; 1 × no test reference and no evidence-doc row naming a real
test (`Y3.8` fails three checks; the other 59 IDs fail one each → 62 check-failures
across 60 IDs). Remediation is to add per-ID evidence rows / explicit ID-to-symbol
mappings — **not** to downgrade or inflate status.

## 6. Documented external and owner gates

These are classification facts, not status changes. They are the reason completion is
not claimed to be absolute.

- **Owner-gated (3):** C11.1, C11.2 (both `blocked`, tier `owner_gated`) and C11.5
  (verified, `owner_approval_required=true`). Gates G6 (source hosting) and owner
  account-level security decisions.
- **External dependency (3):** B4.8, B6.6, C11.8 — verified but dependent on external
  systems (LAN pairing / pinned certs, per-org audit export, Nuitka obfuscation).
- **Dormant / descriptor-only (3):** B6.2, B6.3, B6.5 — verified but inactive,
  owner-directed seams (edition field, enterprise silent-install, compliance pack).
- **External verification gates (audit-accepted limitations):** native Linux/macOS
  sandbox verification; real provider credentials; signing and clean-VM qualification;
  push/release authorization; cross-process grant single-use and DNS-rebinding
  revalidation need host-consumer/durable design. See `AUDIT-REMEDIATION-SUMMARY.md`
  §"Honest accepted limitations" and `FINAL-ENGINEERING-REPORT.md`.
- **Repository gates:** G1 (repo visibility observation, blocks Y6.4) and G6 (source
  hosting, blocks C11.1).

## 7. Promotion checklist (`not_started` → `verified`)

1. Implement the row in real source (or record the new files in the registry).
2. Add and run the automated tests referenced by `test_references`; extend if needed.
3. Exercise the behaviour in the real application/runtime; record what was observed.
4. Update `verification_evidence` with a concrete evidence string (not a plan reference).
5. If the row depends on others, confirm every prerequisite is `verified` first (X0.3).
6. Regenerate `DEPENDENCY-GRAPH.md` and re-check this matrix before claiming completion.
7. For a §5 row, also add a per-ID evidence row that names a real symbol and a real test
   so the strengthened gate can certify it without a limitation.

## 8. Historical provenance (superseded — do not use for planning)

An earlier snapshot of this matrix reported **433 / 430 / 2** (433 verified /
430 not_started / 2 blocked) and a per-ID table of 430 `not_started` rows, with a source SHA of
`c88de4c20ced8a11ceca3c193ce5c3cd39a95119f760647c7243489d7b17ce1b`. That snapshot
predates the backend-completion reconciliation: 421 registry rows were subsequently
attributed to the 20 genuine backend modules and certified, and the registry was
regenerated. The 433/430/2 figures and the 637-row addendum breakdown are retained here
**only as historical provenance**; the normative current counts are in §2, and the
normative remaining rows are in §3–§4.


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
