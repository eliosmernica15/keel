# Production Readiness Matrix — Keel backend, stabilization branch `stabilization/post-promotion-production-2026-11-25`

> **PROVISIONAL REBUILD — the exact final stabilization SHA has not yet been supplied by
> the lead.** This matrix is anchored to the branch named above. The exact commit is held
> as a placeholder in §A and must be filled before this document is cited as authoritative.
> No gate is marked `production_verified` or `pass locally` until evidence exists at that
> exact SHA. Historical candidate evidence is retained but explicitly labelled.

---

## A. Commit identity (exact SHA placeholder — lead to fill)

| Field | Verified value / placeholder |
| --- | --- |
| Authoritative branch | `stabilization/post-promotion-production-2026-11-25` |
| Current baseline tip (verified in this worktree) | `f60b080a1c770608e1ddbf3d888a6e63a7c1b6bb` — `docs(stabilization): record verified baseline and failing CI workflows` |
| **Exact final stabilization SHA** | **`<<LEAD_SUPPLIED_SHA — PLACEHOLDER, NOT YET FILLED>>`** |
| `origin/main` (verified) | `9a63be929d7b364411b856aaf61230817697c410` |
| Prior backend promotion | `779ff942fff9dd106af7d7b3b4b35f95bfc5d2a4` (ancestor of `origin/main`) |
| Stabilization diff vs `origin/main` at baseline | 1 path (`POST-PROMOTION-STABILIZATION-BASELINE.md`) |
| Current version constant | `0.1.1` (`keel/src/keel/__init__.py`, `keel/pyproject.toml`) |
| CI at baseline | All six backend workflows FAIL on main SHA `9a63be92`; step logs no longer retrievable (`POST-PROMOTION-STABILIZATION-BASELINE.md:9-20`) |

**Historical SHAs — NOT current evidence.** `e573273…`, `ac84fee…`, `fe6cdd…`,
`CANDIDATE_HEAD…` tokens, `ecba9d2b…` and any line number keyed to those commits are
historical provenance from the pre-promotion candidate family. A test executed at one of
those commits is **not** evidence for the final stabilization SHA. `PROD-*-EVIDENCE.md`
and `master-plan-v6-*.md` files are cited below only in this historical sense. No
`STAB-*-EVIDENCE.md` file had landed at the baseline tip when this matrix was rebuilt;
`pass locally` is therefore zero until such evidence is attached.

**Stale counts recorded here for provenance only:** 383 / 422 changed paths, 30/30 (also
reported as 20 and 23) action pin counts, 4214 / 4419 / 4437 full-suite pass counts. The
**current** baseline facts are 1 changed path and **31** `uses:` references in
`.github/workflows/*.yml`, all 40-character SHA pins (12 checkout, 10 setup-python,
4 setup-node, 3 upload-artifact, 2 download-artifact). The extra `setup-node` ref
accounts for the 30→31 drift; older 20/23 counts are superseded.

---

## B. Status vocabulary used by this rebuild

| Status | Meaning |
| --- | --- |
| `production_verified` | Real **current** production evidence: deployed instance, live provider call, or signed/published release at the exact final SHA. |
| `pass locally` | Current source **and** test evidence at local scope, produced at the exact final SHA. Historical candidate tests do not qualify. |
| `external_validation_pending` | Mechanism implemented and locally evidenced historically, but an external check, clean-VM run, or live credential round-trip must be repeated at the exact final SHA before closure. |
| `owner_gated` | Cannot be closed by engineering: needs owner signing identity, credentials, authorization, or a governance decision. |
| `blocked` | Hard technical/platform blocker that must be removed before the gate can be attempted (e.g. native macOS runner absent, `sandbox-exec` SIGABRT). |

`production_verified` is **0** and `pass locally` is **0** in §D. That is a provisional
consequence of the missing exact SHA and absent current evidence — **not** a finding that
the code regressed.

`PR-01`..`PR-20` are the stable gate identifiers. Source anchors are file paths only:
line numbers were keyed to historical candidate commits and are deliberately omitted.

---

## C. Authoritative gates

| ID | Subsystem | Requirement | Current source anchor (branch, re-check at final SHA) | Historical evidence (NOT current) | Status | Evidence required to close | Owner |
| --- | --- | --- | --- | --- | --- | --- | --- |
| PR-01 | process | Start/stop Keel deterministically | `keel/src/keel/cli/main.py` (`serve`/`fleet`/`web`), `webapp.py` (`serve`, Ctrl+C), `fleet/scheduler.py` (`start_daemon`) | `master-plan-v6-test-evidence.md`; `BACKEND-OPERATIONS-RUNBOOK.md` §1 | external_validation_pending | Repeat startup/shutdown on exact SHA; clean-VM check 1; add SIGTERM/service path if claimed | Backend ops |
| PR-02 | health | Liveness distinct from readiness | `keel/src/keel/webapp.py` (`/api/health`), `commands.py` (`doctor`), `capability_registry.py` (diagnostics) | `master-plan-v6-cli-surface-evidence.md`; runbook §2 | external_validation_pending | Re-run health/doctor checks on exact SHA; do not claim `/api/ready` | Backend ops |
| PR-03 | readiness | Module health and release evidence | `backend_observability.py` (`health_snapshot`), `scripts/verify_backend_operation.py` (root) | `master-plan-v6-release-acceptance.md`; `FINAL-RELEASE-OPERATIONS.md` | external_validation_pending | Re-run evidence gate with `--strict` on exact SHA; close clean-checkout reproducibility defect | Release owner |
| PR-04 | configuration | Scoped config and env validation | `settings.py`, `cli/main.py` (`settings`, `execpolicy`), `admin_ops.py` | `master-plan-v6-config-contracts-evidence.md` | external_validation_pending | Re-run config suites on exact SHA; force absolute `KEEL_STATE_DIR` in operator paths | Backend ops |
| PR-05 | secrets | Encrypted secrets, presence-only diagnostics | `secret_store.py`, `secret_providers.py`, `cli/main.py` (`secrets`) | `master-plan-v6-secrets-policy-evidence.md` | external_validation_pending | Re-run secret suites on exact SHA; document keyring rotation | Security owner |
| PR-06 | providers | Configuration/validation without fabricated success | `provider_validation.py`, `provider_contracts.py`, `circuit_breaker.py`, `cli/main.py` (`provider validate [--live]`) | `PROD-PROVIDER-EVIDENCE.md` (offline injection only; no live call) | external_validation_pending | Disposable provider credential + live smoke at exact SHA; see §E.1 | Provider owner |
| PR-07 | data | Verified encrypted backup/restore | `backups.py`, `resilience.py`, `capability_registry.py` (`release.backups.*`) | `master-plan-v6-db-persistence-evidence.md`, `master-plan-v6-recovery-evidence.md` | external_validation_pending | Re-run backup/restore tests on exact SHA; no `keel backup` CLI exists | Data owner |
| PR-08 | data | Forward migration, honest rollback limits | `fleet/db.py` (`_migrate`, v1..v11), `config_contracts.py` (`SchemaApplySeam.apply`) | `master-plan-v6-db-persistence-evidence.md` | external_validation_pending | Re-run migration tests on exact SHA; implement or formally waive down-migration | Data owner |
| PR-09 | release | Installer rollback / failed-start auto-rollback | `release/updater.py` (`atomic_install`, `rollback`), `start_health.py`, `e5_backend.py` | `PROD-ROLLBACK-EVIDENCE.md` (6 real-code drill tests at historical candidate) | external_validation_pending | Disposable-VM check 5 at exact SHA; see §E.2 | Release owner |
| PR-10 | logging | Locatable, tamper-evident, redacted log | `backend_observability.py`, `redaction.py` | `master-plan-v6-reliability-contracts-evidence.md` | external_validation_pending | Re-run chain/redaction tests on exact SHA; define rotation | Backend ops |
| PR-11 | diagnostics | Redacted diagnostic export | `diagnostics.py`, `cli/main.py` (`doctor --bundle`) | `diagnostics.py` docstring, `master-plan-v6-test-evidence.md` | external_validation_pending | Re-run bundle redaction tests on exact SHA; manual bundle review | Security owner |
| PR-12 | workers | Scheduler/gateway recovery | `fleet/scheduler.py`, `gateway.py` | `master-plan-v6-gate-scheduler-evidence.md`, `master-plan-v6-fleet-events-evidence.md` | external_validation_pending | Re-run scheduler tests on exact SHA; no multi-day soak exists | Fleet owner |
| PR-13 | security | Stop unsafe execution / change posture | `fleet/turn_core.py`, `webapp.py` (`kill-switch`), `gateway.py`, `execpolicy` CLI | `master-plan-v6-security-contracts-evidence.md`, `master-plan-v6-win-network-evidence.md` | external_validation_pending | Re-run Windows enforcement tests on exact SHA; native Linux/macOS handled under PR-19 | Security owner |
| PR-14 | security | Revoke credentials / disable integration | `cli/main.py` (`mcp`/`tools` revoke), `settings_store.py`, `pairing.py`, `config_contracts.py`, `release.revoke` | `PROD-REVOCATION-EVIDENCE.md` (7 local tests at historical candidate; gap G1 reported) | external_validation_pending | Live revoke round-trip at exact SHA; owner decision on Y3.9 descriptor gap G1; see §E.3 | Security owner |
| PR-15 | security | Preserve forensic evidence | `backend_observability.py` (`verify_chain`), `diagnostics.py` | `master-plan-v6-recovery-evidence.md` | external_validation_pending | Re-run chain/retention tests on exact SHA; define retention policy | Security owner |
| PR-16 | deployment | Clean setup and dependency install | `pyproject.toml`, `keel/scripts/check_version_sync.py`, `scripts/verify_clean_setup.py`, `scripts/verify_backend_operation.py` | `PROD-CLEAN-SETUP-EVIDENCE.md` (clean-venv `pass` at historical candidate; release audit disputes reproducibility) | external_validation_pending | Repeat clean-checkout install + full suite on exact SHA; close audit finding; see §E.4 | Release owner |
| PR-17 | deployment | Upgrade and recovery path | `release/updater.py`, `release/verify.py`, `e5_backend.py`, `release/cli.py` | `PROD-ROLLBACK-EVIDENCE.md` (local drill, ephemeral key, historical) | external_validation_pending | Signed clean-VM upgrade/rollback at exact SHA with owner signing identity; see §E.5 | Release owner |
| PR-18 | monitoring | Real signals, redaction, bounded views | `backend_observability.py` (`diagnostic_report`), `admin_page.py`, `circuit_breaker.py`, `cli/main.py` (`costs status`) | `master-plan-v6-reliability-contracts-evidence.md` | external_validation_pending | Re-run signal tests on exact SHA; no exporter/pager exists and thresholds are unapproved | Backend ops |
| PR-19 | platform | Native Linux/macOS execution and installers | `sandbox_linux.py`, `sandbox_macos.py`, `os_sandbox.py` | `PROD-PLATFORM-EVIDENCE.md` (Windows native verified; Linux WSL2 6.6.87.2 scoped; macOS none) | blocked | Native macOS runner incl. macOS 26 `sandbox-exec` SIGABRT fix; bare-metal/Linux CI runner; DMG/ZIP/AppImage/deb; see §E.6 | Platform owner |
| PR-20 | governance | Live providers, signing, release authorization | `release/signing.py`, `release/publish.py`, `.github/workflows/signing-readiness.yml` | `PROD-SUPPLY-CHAIN-EVIDENCE.md` (31 SHA-pinned action refs at current baseline; unsigned installers); owner gates | owner_gated | Owner signing identity, CI sign job, provider credentials, push/publish authorization, 2FA/branch protection; see §E.7 | Owner |

---

## D. Gate classification summary (provisional)

| Classification | Count | Requirement IDs |
| --- | ---: | --- |
| `production_verified` | 0 | none — no current deployed instance, live provider call, or signed published release |
| `pass locally` | 0 | none — no evidence produced at the exact final SHA; see §A |
| `external_validation_pending` | 18 | PR-01..PR-18 |
| `owner_gated` | 1 | PR-20 |
| `blocked` | 1 | PR-19 |
| **Total mandatory gates** | **20** | PR-01..PR-20 |

Superseded counts (retained for provenance, **do not cite**): the earlier matrix summary
claimed `pass 17 / unverified 3 / blocked 2` while listing only 13 pass IDs and counting
PR-19 in both `unverified` and `blocked`; the earlier report claimed
`pass 13 / unverified 5 / blocked 2`. Both were keyed to historical candidate SHAs and
disagreed with their own row statuses. This rebuild replaces them.

---

## E. Reconciliation of the seven named gates

### E.1 PR-06 — providers
`PROD-PROVIDER-EVIDENCE.md` is explicit: 55 offline injection tests, **no real provider
request**, and a documented integration gap (production callers have not opted into the
new policy layer). Required credentials are named but no values were used. **Status:
external_validation_pending.** It is not `owner_gated` only because the executing party
could supply a disposable credential; it is not `pass locally` because the live gap is
open even in the historical evidence, and nothing was re-run at the final SHA.

### E.2 PR-09 — rollback
`PROD-ROLLBACK-EVIDENCE.md` records six real-code tests (real loopback server, signed
ephemeral manifest, real `atomic_install`/`rollback`, SQLite canary preserved, four
fail-closed cases) and states verbatim: "locally closed at the code-path level; full
matrix gate still requires the disposable-VM check 5" and "Classification: pass locally /
external validation pending. Do **not** record this as `production_verified`." That test
ran at historical candidate `ac84fee`; it is retained as historical. **Status:
external_validation_pending.**

### E.3 PR-14 — revocation
`PROD-REVOCATION-EVIDENCE.md` records seven real local tests (provider key removal clears
env and ciphertext, MCP connector/approval disable, pairing revoke, approval-token revoke,
redacted audit chain) and one **negative** test proving the Y3.9 sign-out descriptor does
**not** delete stored credentials (gap G1). Historical verdict: locally achieved gates
closed, live provider revoke still untested. **Status: external_validation_pending** with
an owner decision required on gap G1 (implement real purge or accept a documented waiver).

### E.4 PR-16 — clean setup
`PROD-CLEAN-SETUP-EVIDENCE.md` records a real hash-verified install in two disposable
venvs, 7/7 runtime checks and 141-142 tests "exercised with failures characterized", and
concludes `pass` at local scope while explicitly denying `production_verified`. It is
keyed to historical `ac84fee`. `master-plan-v6-release-audit.md` and
`REVIEW-FINAL-QUALITY.md` dispute clean-checkout reproducibility, and the stabilization
baseline records all backend CI workflows failing on `9a63be92`. **Status:
external_validation_pending** — repeat on exact final SHA before any `pass locally`.

### E.5 PR-17 — upgrade/recovery
Same historical drill as PR-09 plus the interrupted-swap recovery test, using an ephemeral
Ed25519 key. No VM tooling, no built installers, no production signing identity were
available. The signed clean-VM `0.1.0 → 0.1.1` upgrade is outstanding. **Status:
external_validation_pending**, with a signing dependency that is owner-gated under PR-20.

### E.6 PR-19 — native platforms
`PROD-PLATFORM-EVIDENCE.md` verifies Windows natively (scoped) and the integrated Linux
Landlock+seccomp backend on WSL2 kernel 6.6.87.2 with four conformance failures, while
Linux CI/bare-metal remains unverified. macOS was not executed; read isolation is BLOCKED
by `sandbox-exec` SIGABRT on macOS 26. This is a hard blocker, not an owner preference.
**Status: blocked.**

### E.7 PR-20 — governance, signing, live providers
Action pinning is currently 31/31 SHA refs across eight workflows (current baseline
verification), but installers remain unsigned, no `KEEL_RELEASE_SIGNING_KEY` identity
exists, no live provider credential exists, and GitHub Free private-repo branch
protection is unavailable (403/404/422). These are owner/plan actions. **Status:
owner_gated.** Do not downgrade to `pass locally` on the strength of pinning or build
integrity alone.

---

## F. Historical passages retained explicitly

The following statements belong to the pre-promotion candidate family and are preserved
only as provenance in `PRODUCTION-READINESS-REPORT.md` and the four backend runbooks:
"Candidate `CANDIDATE_HEAD` / `e573273` / `ac84fee`", branch `agent/prod-ops`, the
4214/4419/4437 suite figures, the 383/422 path counts, "no push performed", "NOT PROMOTED
TO MAIN", and the subsequent "owner-authorized promotion" note. The current state is
recorded in §A and in `POST-PROMOTION-STABILIZATION-BASELINE.md`.

---

## G. Honest scope note

This matrix covers backend/harness operations only. No frontend, no source/test/workflow
change, and no push are part of this rebuild. A gate may move to `pass locally` or
`production_verified` only when evidence at the exact final stabilization SHA is attached
and the owner signs off. Until then the counts in §D are the authoritative provisional
verdict.
