# FINAL INDEPENDENT ACCEPTANCE — REVIEWER SHELL

> **PLACEHOLDER SHELL — NOT A VERDICT.** Every `<<REVIEWER_SUPPLY: …>>` below must be
> filled with a result the lead/independent reviewer actually observed at the SHA they
> reviewed. Leave a field unfilled rather than inferring a pass; do not remove the field
> marker when recording a value. No result has been supplied by this agent.
>
> Baseline for comparison: `35fb2b8abfd784393b2b252e2b9e2927aba817dd` (tree identical
> to `c512f87971a02b05d9a9422338522f66495c0eeb`). Vocabulary:
> `FINAL-PRODUCTION-READINESS-MATRIX.md` §B. Open external actions:
> `FINAL-OWNER-ACTIONS.md` A1–A5.

## 1. Review identity

| Field | Reviewer-supplied value |
| --- | --- |
| Reviewer / worktree | `<<REVIEWER_SUPPLY: name, worktree, branch>>` |
| Exact SHA reviewed | `<<REVIEWER_SUPPLY: 40-hex SHA + date>>` |

## 2. Results to supply

| Result | Baseline to compare against | Reviewer-supplied value |
| --- | --- | --- |
| Full-suite counts and exit at reviewed SHA | `4610 passed / 0 failed / 54 skipped`, exit 0 | `<<REVIEWER_SUPPLY: counts, exit>>` |
| Governance gates | registry OK 865; strict 421/421 exit 0; license OK; dep graph FRESH; v0.1.1; YAML 8/8; pins 40/40 | `<<REVIEWER_SUPPLY: pass/fail per gate>>` |
| Gate changes vs matrix §C | 16 PINV / 2 EXTP / 1 OWNR / 1 BLCK / 0 PVE / 0 NIMP = 20 | `<<REVIEWER_SUPPLY: gate IDs changed + reason, or "no change">>` |
| Owner actions A1–A5 | none performed | `<<REVIEWER_SUPPLY: confirmation + evidence checked>>` |

## 3. Verdict — select exactly one (reviewer only)

- [ ] `ACCEPT_AS_RECORDED`
- [ ] `ACCEPT_WITH_CORRECTIONS` — corrections in §4
- [ ] `BLOCK` — finding in §4
- [ ] `NOT_REVIEWED` — shell intentionally left unfilled

## 4. Findings (reviewer only)

| Gate / document | Finding (file:line or command) | Required correction |
| --- | --- | --- |
| `<<REVIEWER_SUPPLY: id or none>>` | `<<REVIEWER_SUPPLY: observation or none>>` | `<<REVIEWER_SUPPLY: action or none>>` |

## 5. Sign-off

`<<REVIEWER_SUPPLY: production authorized / not authorized + reason; name; date>>`

**Note:** an unfilled shell is not an approval. No verdict, count, SHA, finding or
signature has been invented here.
