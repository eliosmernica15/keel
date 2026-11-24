# Whole-project master-plan inventory (non-generated)

This is a **tracking and reconciliation document**, not a generated registry. The authoritative registry is `PLAN-INDEX.json` (865 features) and its generated projection `parity.json`; neither is hand-edited here. The frontend-only evidence remains in `UI-REQUIREMENTS-MATRIX.md` (150 criteria, 131 verified).

## 1. Registry-derived baseline (read, not edited)

`PLAN-INDEX.json` reports:

| Status | Count |
|---|---:|
| verified | 854 |
| not_started | 9 |
| blocked | 2 |
| **Total** | **865** |

Registry-derived verified percentage: 854/865 = **98.7 %**. This is a registry claim, not a fresh independent verification of all 865 acceptance criteria; the QA workstream samples and verifies the remaining/risky items rather than blindly inheriting statuses.

## 2. Non-verified requirements (full list from the registry)

| ID | Status | Priority | Requirement | Project area | Owner | Test evidence required |
|---|---|---|---|---|---|---|
| C11.1 | blocked | P0 | Source-hosting caveats to decide (GitHub free-plan branch protection / secret controls) | Governance / external | owner decision | Documented owner decision; no repo-visibility change without approval |
| C11.2 | blocked | P0 | Repo security hygiene (2FA, signed commits, least-privilege tokens, pinned Actions) | Governance / external | owner decision | Settings audit; cannot be performed by agent |
| D6.14 | not_started | P1 | Tests describe behaviour; change obsolete behaviour together with tests | Builder process | Agent H | Existing test changes must accompany behaviour changes |
| D6.17 | not_started | P1 | Agent Notes (ADR-like) for durable rationale only; archived notes frozen | Builder process | Agent H | Docs audit |
| D6.18 | not_started | P1 | Prefer maintained dependencies over hand-rolling when they delete owned code/tests | Builder process | Agent H | Dependency review note |
| D6.2 | not_started | P1 | Plugins, not loop changes: new behaviour attaches to documented extension points | Builder process | Agent H | Architecture doc check |
| D6.20 | not_started | P1 | Run only relevant checks locally; match evidence to change | Builder process | Agent G | Local verification practice |
| D6.21 | not_started | P1 | PR hygiene: labels, force-with-lease, PR description template | Builder process | Agent H | PR/branch audit |
| D6.23 | not_started | P1 | Defensive-patterns doc read before touching package/remote/client-state surfaces | Builder process | Agent H | Docs audit |
| W1.18 | not_started | P0 | MIT license + `THIRD_PARTY_NOTICES.md` | Legal / licensing | Agent H | File presence and accuracy |
| Y6.4 | not_started | P0 | Repo visibility public, 0 stars/forks | Governance / external | owner decision | **Do not change** — prior instructions prohibit visibility changes |

## 3. Areas of work launched in this round

| Agent | Workstream | Ownership (initial) |
|---|---|---|
| A | Frontend residual + real-browser accessibility | `fleet-next/**` tests/docs only after frontend freeze; no new feature rewrites |
| B | Backend services / Python failure baseline comparison | `keel/tests/**` (new focused tests), `keel/src/keel/**` only for proven regressions |
| C | Agent execution / orchestration verification | read-only audit + focused tests in `keel/tests/**` (distinct filenames) |
| D | Providers / integrations / local test provider | `keel/src/keel/providers/**` + tests only for proven gaps |
| E | Desktop packaging (Electron/Tauri) | `keel/desktop-app/**`, `keel/desktop/src-tauri/**`, packaging docs |
| F | Security / trust / reliability verification | security tests + docs |
| G | Independent QA | QA docs, test infrastructure, defect reports |
| H | Documentation / parity / licensing | `keel/docs/**`, `THIRD_PARTY_NOTICES.md`, legal docs (never generated files) |

File ownership is exclusive per agent; the lead integrates and pushes accepted batches.

## 4. Previously reported blockers under active investigation

Electron packaged renderer, Tauri build (`link.exe` missing), real provider turn, Python 7 failures baseline comparison, bridge 504 root cause, long-history performance, screen-reader, and real 200 % browser zoom. Results are recorded in `UI-REQUIREMENTS-MATRIX.md` and will be reconciled here as evidence lands.

## 5. Progress calculation (initial, this round)

Using registry statuses as the starting inventory (not yet independently re-verified):
- Applicable requirements: 865 − 2 blocked − 1 external visibility = 862
- Verified: 854 → 854/862 = **99.1 %**
- Remaining implementation: 9/862 = **1.0 %**
- Blocked: 2/862 = **0.2 %** (plus external environment gates tracked separately)

These percentages will be re-calculated after independent verification. Do not treat them as proof of whole-product production readiness.
