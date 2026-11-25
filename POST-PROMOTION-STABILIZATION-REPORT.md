# Post-promotion stabilization report — FINAL RESULTS TO BE SUPPLIED BY LEAD

> **STATUS: SHELL / NOT FINAL.** This file is a structure for the lead to complete once
> the exact final stabilization commit is designated and `STAB-*-EVIDENCE.md` files land.
> Fields marked `<<LEAD_SUPPLIED>>` are placeholders. Do not treat any placeholder as a
> result, and do not move a gate to `pass locally` or `production_verified` without
> evidence attached at the exact SHA.

## 0. Reporting rules

1. Anchor every result to the **exact final stabilization SHA** — never to a historical
   candidate hash (`CANDIDATE_HEAD…`, `e573273…`, `ac84fee…`, `fe6cdd…`) or to the
   baseline tip alone.
2. A test run at a prior commit is **[HISTORICAL]** and is not current evidence.
3. Status vocabulary is that of `PRODUCTION-READINESS-MATRIX.md` §B:
   `production_verified` / `pass locally` / `external_validation_pending` /
   `owner_gated` / `blocked`.
4. Keep the five readiness states separate: backend implementation complete /
   backend locally verified / backend production-ready / desktop release-ready /
   production deployment completed.
5. Live providers, native macOS and signing remain external unless real evidence exists.

## 1. Git state

| Field | Value |
| --- | --- |
| Exact final stabilization SHA | `<<LEAD_SUPPLIED_SHA — PLACEHOLDER>>` |
| Stabilization branch | `stabilization/post-promotion-production-2026-11-25` |
| Baseline tip recorded at start | `f60b080a1c770608e1ddbf3d888a6e63a7c1b6bb` |
| `origin/main` | `9a63be929d7b364411b856aaf61230817697c410` (verified at baseline; re-verify at finalization) |
| Prior backend promotion | `779ff942fff9dd106af7d7b3b4b35f95bfc5d2a4` (ancestor of main) |
| Diff vs `origin/main` at baseline | 1 path; **expected final path count:** `<<LEAD_SUPPLIED>>` |
| Action refs in `.github/workflows/*.yml` at baseline | 31, all SHA-pinned; **expected final count:** `<<LEAD_SUPPLIED>>` |
| Push / publish / deploy performed | `<<LEAD_SUPPLIED — default: NO>>` |

## 2. CI workflow results (re-run at exact SHA)

Baseline (from `POST-PROMOTION-STABILIZATION-BASELINE.md:9-20`): all six backend workflows
FAIL on main `9a63be92`; step logs were unavailable (`BlobNotFound`). Re-run and fill in.

| Workflow | Baseline result | Final run ID | Final result | Root cause / fix evidence |
| --- | --- | --- | --- | --- |
| Python tests | failure | `<<LEAD>>` | `<<LEAD>>` | `<<LEAD>>` |
| Secret scan | failure | `<<LEAD>>` | `<<LEAD>>` | `<<LEAD>>` |
| Offline + license gates | failure | `<<LEAD>>` | `<<LEAD>>` | `<<LEAD>>` |
| Build desktop installers | failure | `<<LEAD>>` | `<<LEAD>>` | `<<LEAD>>` |
| Provider validation | failure | `<<LEAD>>` | `<<LEAD>>` | `<<LEAD>>` |
| Verify installed packages | failure | `<<LEAD>>` | `<<LEAD>>` | `<<LEAD>>` |

No CI result may be claimed fixed without a local reproduction and a fresh run.

## 3. Test results at exact SHA

| Suite / command | Historical figures (NOT current) | Current result at exact SHA |
| --- | --- | --- |
| `python -m pytest -q -o faulthandler_timeout=120` | 4214/48/0, 4419/8/51, 4437/5/51 at different commits | `<<LEAD_SUPPLIED: passed / failed / skipped / subtests / duration>>` |
| `scripts/verify_backend_operation.py --strict` | 421/421 traceable at historical candidate | `<<LEAD_SUPPLIED>>` |
| `scripts/verify_v6_audit.py` | CONSISTENCY OK (865 rows) | `<<LEAD_SUPPLIED>>` |
| `keel/scripts/check_version_sync.py` | OK, version 0.1.1 | `<<LEAD_SUPPLIED>>` |
| Clean-checkout install (`scripts/verify_clean_setup.py`) | 7/7 at historical `ac84fee` | `<<LEAD_SUPPLIED>>` |

Characterize every failure as code defect, environmental, artifact-dependent, or
order/env pollution; do not delete or weaken tests to obtain green.

## 4. Gate classification at exact SHA

Copy the final counts from `PRODUCTION-READINESS-MATRIX.md` §D after re-verification.

| Classification | Count | Gate IDs |
| --- | ---: | --- |
| `production_verified` | `<<LEAD>>` | `<<LEAD>>` |
| `pass locally` | `<<LEAD>>` | `<<LEAD>>` |
| `external_validation_pending` | `<<LEAD>>` | `<<LEAD>>` |
| `owner_gated` | `<<LEAD>>` | `<<LEAD>>` |
| `blocked` | `<<LEAD>>` | `<<LEAD>>` |
| **Total** | **20** | PR-01..PR-20 |

## 5. Seven named gates — final reconciliation

For each, attach the exact-SHA evidence file and mark the final status. Historical
evidence is already summarized in matrix §E; it does not close the gate.

| Gate | Historical evidence | External / owner dependency | Final status (`<<LEAD>>`) | Evidence file at exact SHA |
| --- | --- | --- | --- | --- |
| PR-06 providers | `PROD-PROVIDER-EVIDENCE.md` — offline injection only, no live call | Disposable/free-tier credential, `KEEL_*_API_KEY`, live `--live` round-trip | `<<LEAD>>` | `<<LEAD>>` |
| PR-09 rollback | `PROD-ROLLBACK-EVIDENCE.md` — 6 real-code tests at old candidate | Disposable-VM check 5 (install 0.1.0→0.1.1, 3 failed starts) | `<<LEAD>>` | `<<LEAD>>` |
| PR-14 revocation | `PROD-REVOCATION-EVIDENCE.md` — 7 local tests, gap G1 negative test | Live provider revoke round-trip; owner decision on descriptor purge/waiver | `<<LEAD>>` | `<<LEAD>>` |
| PR-16 clean setup | `PROD-CLEAN-SETUP-EVIDENCE.md` — local `pass` at old candidate | Clean-checkout reproducibility finding; exact-SHA re-run | `<<LEAD>>` | `<<LEAD>>` |
| PR-17 upgrade/recovery | `PROD-ROLLBACK-EVIDENCE.md` — ephemeral-key drill | Signed clean-VM upgrade/rollback + owner signing identity | `<<LEAD>>` | `<<LEAD>>` |
| PR-19 native platforms | `PROD-PLATFORM-EVIDENCE.md` — Windows scoped, Linux WSL2 scoped, macOS none | Native macOS runner, macOS 26 `sandbox-exec` SIGABRT fix, Linux CI/bare-metal runner, DMG/ZIP/AppImage/deb | `<<LEAD>>` | `<<LEAD>>` |
| PR-20 governance | `PROD-SUPPLY-CHAIN-EVIDENCE.md` — 31/31 SHA pins at baseline | Signing identity, CI sign job, provider credentials, push/publish authorization, 2FA/branch protection | `<<LEAD>>` | `<<LEAD>>` |

## 6. External blockers carried forward

- Live provider credentials (names only, no values).
- Signed clean-VM upgrade/rollback and a production signing identity.
- Native macOS runner; macOS 26 read isolation blocked by `sandbox-exec` SIGABRT.
- Native Linux CI/bare-metal runner beyond historical WSL2 scope.
- GitHub Free private-repo branch protection (403/404/422) and 2FA (owner account).
- Vercel build-rate-limit is a frontend hosting concern, separate from backend gates.

## 7. Five-state final verdict (lead to complete)

| State | Final verdict | Basis |
| --- | --- | --- |
| Backend implementation complete | `<<LEAD>>` | `<<LEAD>>` |
| Backend locally verified | `<<LEAD>>` | `<<LEAD>>` |
| Backend production-ready | `<<LEAD>>` | `<<LEAD>>` |
| Desktop release-ready | `<<LEAD>>` | `<<LEAD>>` |
| Production deployment completed | `<<LEAD>>` | `<<LEAD>>` |

## 8. Sign-off

| Role | Name | Decision | Date |
| --- | --- | --- | --- |
| Lead | `<<LEAD>>` | `<<LEAD>>` | `<<LEAD>>` |
| Independent reviewer | `<<LEAD>>` | `<<LEAD>>` | `<<LEAD>>` |
| Owner (for owner-gated items) | `<<LEAD>>` | `<<LEAD>>` | `<<LEAD>>` |

> Promotion is not authorized while any gate remains `external_validation_pending`,
> `owner_gated`, or `blocked`, unless the owner records an explicit, reviewable
> authorization that names each waived gate. Historical authorizations apply to their
> own commits and do not waive gates at the exact final stabilization SHA.
