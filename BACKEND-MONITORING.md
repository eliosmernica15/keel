# Backend Monitoring — Keel

**Branch:** `stabilization/post-promotion-production-2026-11-25`
**Exact final stabilization SHA:** `<<CANDIDATE_HEAD_REFERENCE — placeholder; see matrix §A>>`
This document describes the signals the code **actually emits** and how to read them.
It does not invent metrics, exporters, dashboards, or alert rules that do not exist in
the repository. Proposed thresholds at the end are explicitly **proposed, not
owner-approved** and are not implemented configuration.

**Readiness states (do not conflate):** backend implementation **complete**; backend
locally verified **historical only**, not current; backend production-ready **no**;
desktop release-ready **no**; production deployment completed **no**. Monitoring is a
set of local signals, not a deployed observability stack; see
`PRODUCTION-READINESS-MATRIX.md` §§B/D (PR-18 is `external_validation_pending`).

Sources: `keel/src/keel/backend_observability.py`, `keel/src/keel/webapp.py`,
`keel/src/keel/start_health.py`, `keel/src/keel/diagnostics.py`,
`keel/src/keel/redaction.py`, `keel/src/keel/fleet/scheduler.py`,
`keel/src/keel/gateway.py`, `keel/src/keel/circuit_breaker.py`,
`keel/src/keel/cost_caps.py`, `keel/src/keel/admin_page.py`.

---

## 1. Health vs readiness — keep them separate

| Term | Real signal | Meaning | Does not mean |
| --- | --- | --- | --- |
| **Liveness / health** | `GET /api/health` → `{"ok": true, "version": "0.1.1"}` (`webapp.py:6`, `webapp.py:378`) | The token-gated loopback HTTP process is up. | Backend modules import cleanly, DB healthy, provider reachable, or release-ready. |
| **Backend readiness** | `health_snapshot(state_root, modules)` — per-module `imported`, `import_status`, `declared_features`, `error_count`, `healthy`, plus `chain_ok` and overall `healthy` (`backend_observability.py:481-527`); `keel capability invoke core.diagnostics` (`capability_registry.py:91-95`) | All 20 modules import and the event chain verifies. | That the install is signed, provider-live, or clean-VM validated. |
| **Startup readiness** | `keel doctor` (`commands.py:189-212`) and `keel capability invoke release.health` (`start_health.py:40-50`) | Tools present, provider keys masked-present, state dirs; consecutive failed-start count and `rollback` flag. | That the bridge is currently serving. |
| **Release readiness** | `keel doctor --bundle`, `python scripts/validate_desktop.py --dist dist`, `python scripts/verify_backend_operation.py`, `python -m keel.release integrity ...` | Evidence for a release decision. | A production release: all owner gates remain open (`BACKEND-DEPLOYMENT.md` §10). |

There is **no** `/api/ready` endpoint and no readiness probe in this codebase. Do not
configure one that does not exist.

---

## 2. What to watch (real surfaces)

### a. Event log and its integrity — `<state_root>/observability.jsonl`

- Append-only JSONL with deterministic monotonic `seq`, UTC `ts`, `kind`, `session_id`,
  optional `task_id`/`agent_id`/`feature_id`/`module`, `correlation_id`, `data`,
  `prev_hash` and `hash` (SHA-256 chain), `0o600` appends with `fsync`
  (`backend_observability.py:1-16`, `344-425`).
- `verify_chain(state_root)` checks sequence continuity, hash linkage and per-event
  digest; a corrupt or malformed chain is **never extended and never returned as
  trusted events** (`backend_observability.py:276-323`, `386-392`, `436-441`).
- `read_events(state_root, kind=..., session_id=..., since_seq=...)` returns verified
  events oldest-first (`backend_observability.py:428-449`).
- `diagnostic_report(state_root)` returns `chain` (with `ok`, `event_count`,
  `first_seq`, `last_seq`, `error`), `chain_status` (`ok` / `corrupt`),
  `total_events`, `counts_by_kind`, `counts_by_session`, and a bounded tail of recent
  errors (`backend_observability.py:530-566`). These are Python APIs / capability
  surfaces, not a CLI subcommand.

### b. Error events

- `record_event(kind="error", ...)` is the typed way to record a backend error;
  `health_snapshot()` attaches recorded `error` events to their module
  (`backend_observability.py:361-425`, `491-517`).
- `diagnostic_report()` exposes at most `_RECENT_ERROR_LIMIT = 20` recent errors,
  already redacted (`backend_observability.py:45`, `551-566`). This is the **only
  bounded view**; the log file itself has no automatic rotation in this code.

### c. Startup health — `<state_root>/start-health.json`

- `record_start()` increments a consecutive-failure counter per version and returns
  `rollback: true` when failures ≥ `max(1, threshold)` with default threshold 3
  (`start_health.py:15`, `40-50`). Successful starts reset the counter.
- Read it with `keel capability invoke release.health --params '{"state_root":"..."}'`
  (`capability_registry.py:1735-1739`). The admin page aggregates it into an alerts
  list (`admin_page.py:17-30`, `52-72`).

### d. Workers / gateway

- `GET /api/gateway` → `Gateway.status()`: `running`, `ticks`, `started_at`, `uptime_s`
  (`webapp.py:519`, `gateway.py:25-33`). A gateway thread that stops incrementing
  `ticks` while `running` is stale is suspicious; a failed tick is swallowed by design
  (`gateway.py:42-50`).
- Fleet scheduler outcomes are durable: `skipped_missed`, `failed`, `completed`,
  timeout (`terminal_reason=timeout`), approval-denied / timed-out recorded as failed
  (`scheduler.py:81-94`, `194-238`, `241-304`). Daemon interval 20 s
  (`scheduler.py:35`, `340`); timeout `KEEL_FLEET_ROUTINE_TIMEOUT_S`, default 600
  (`scheduler.py:40-44`).

### e. Provider health

- `keel provider validate` produces per-provider `PASS | FAIL | SKIP` checks:
  `auth_present` (presence only), `model_discovery_static`, `tool_capability`,
  `streaming_capability`, and `live_provider` SKIP unless `--live` plus a configured
  credential (`provider_validation.py:40-58`, `106-132`).
- `keel provider smoke <name>` exercises a real adapter through the registry
  (`cli/main.py:1235-1255`). **[HISTORICAL]** no live credential was configured on the
  candidate host (`PROD-PROVIDER-EVIDENCE.md`). **Current classification:** PR-06 is
  `external_validation_pending`; SKIP is not a pass and no live result may be reported
  as green without a recorded round-trip at the exact final stabilization SHA.
- Circuit breaker: `health_score()`, `health` field in provider status
  (`keel/src/keel/circuit_breaker.py:100-112`); provider registry status is exposed at
  `GET /api/providers` (`webapp.py:7`, `webapp.py:384`).
- Cost caps: `keel costs status` reports per-provider caps and daily/monthly totals
  (`cli/main.py:478-521`).

### f. Diagnostics bundle

- `keel doctor --bundle [--file PATH]` writes a redacted ZIP containing
  `diagnostics.json` and `README.txt` (`diagnostics.py:49-57`, `cli/main.py:177-189`).
  It is local-only; Keel never uploads it (`diagnostics.py:1-6`).

---

## 3. Alert-worthy signals (what actually indicates trouble)

1. `verify_chain()` returns `ok: false` / `chain_status: corrupt` — tampering,
   truncation, or malformed JSONL. Appends fail closed (`backend_observability.py:319-323`, `386-392`).
2. `health_snapshot().healthy == false` — a backend module failed to import, or the
   chain is corrupt. A module is reported `healthy: false`, never silently healthy
   (`backend_observability.py:499-524`).
3. `release.health` shows `rollback: true` (≥3 consecutive failed starts)
   (`start_health.py:40-50`).
4. Rising `counts_by_kind["error"]` or `error_count` for a specific module in
   `diagnostic_report()` / `health_snapshot()`.
5. `GET /api/gateway` shows `running: false` when a scheduler is expected, or `ticks`
   stops advancing (`gateway.py:25-50`).
6. Fleet routine outcomes `failed` / `skipped_missed` / `terminal_reason=timeout`
   clustering — see `scheduler.py:81-94`, `194-304`.
7. `db_integrity("~/.keel/fleet.db") == false` — `PRAGMA integrity_check` not `ok`
   (`resilience.py:87-90`).
8. `keel provider validate` shows `FAIL` in static checks or `FAIL` in a live check
   with real credentials; SKIP without credentials is **not** a pass
   (`provider_validation.py:40-58`, `97-102`).
9. Unexpected `403` on `/api/*` — token rotation or Origin mismatch
   (`webapp.py:253-280`, `228-232`).
10. Web UI never reachable at startup — check that the port is free and that the loopback
    URL was printed (`webapp.py:1311-1320`).

No alerting pipeline, exporter, or on-call integration exists in the repository. These
are signals for an operator to poll with the APIs above; wiring them to a pager is an
owner decision, not an implemented feature.

---

## 4. Redaction and bounded logs — what is guaranteed

- **Before persistence:** `record_event()` deep-redacts the whole event with
  `keel.redaction.redact_text` detection; sensitive dict keys (`api_key`, `token`,
  `password`, `secret`, `authorization`, `pin`, ...) cause the entire value to become
  `[REDACTED]` (`backend_observability.py:191-224`, `408`; `redaction.py:17-53`).
- **In diagnostics:** env vars whose names contain `KEY`, `TOKEN`, `SECRET`,
  `PASSWORD`, `CREDENTIAL` are replaced with `••<len> chars`; no conversation content
  is included (`diagnostics.py:19-45`). `keel doctor` uses `<set N chars>` / `<unset>`
  for provider keys (`commands.py:185-208`).
- **In provider checks:** `auth_present` reports presence only; the value is never
  exposed (`provider_validation.py:43-47`).
- **In config:** secret values are AES-256-GCM encrypted at rest; provider config stores
  no values (`secret_store.py:1-8`, `secret_providers.py:1-12`, `143-160`).
- **Bounded view:** `diagnostic_report()` returns the last 20 error events
  (`backend_observability.py:45`, `551-566`). The raw JSONL is append-only and grows
  unbounded; retention/rotation must be handled by the operator, not assumed from code.
- **Web logs:** deliberately suppressed (`webapp.py:1308-1309`), so the bridge does not
  duplicate secrets into stderr.

Redaction patterns cover private keys, OpenRouter/OpenAI/Google/AWS/GitHub/Slack
tokens, JWTs, inline `api_key=`-style assignments and `Bearer`/`Basic` values
(`redaction.py:18-53`). A new credential format not in this vocabulary is not detected;
review the bundle manually before sharing.

---

## 5. Proposed operational targets (not owner-approved, not implemented)

The following are **proposals only**. They are not defaults, not configured anywhere,
and must not be reported as existing behavior or as accepted service levels.

| Proposed target | Rationale | Owner decision required |
| --- | --- | --- |
| Poll `GET /api/health` every 30 s for liveness | Cheap loopback check | Yes |
| Alert on any `verify_chain().ok == false` | Fail-closed integrity signal | Yes |
| Alert when failed-start counter reaches 2 (before the code's rollback threshold of 3) | Early warning | Yes |
| Alert on `health_snapshot().healthy == false` | Module import failure | Yes |
| Review `diagnostic_report()` error counts hourly | Bound view is last 20 errors | Yes |
| Rotate `KEEL_TOKEN` on suspected client compromise via `POST /api/kill-switch` | Real revocation lever (`webapp.py:722-728`) | Yes |
| Define a retention window for `observability.jsonl` | No rotation exists in code | Yes |

Until an owner approves and implements these, the only honest statement is: **the
signals exist; the monitoring policy does not.**
