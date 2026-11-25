# Production hardening evidence — backend observability

**Branch:** `agent/prod-observe` · **Candidate HEAD:** `e573273` ·
**Worktree:** `C:\Users\Admin\.local\share\opencode\worktree\production\observe`

**Files owned / changed**

- `keel/src/keel/backend_observability.py` (hardened; 479 → 1186 lines)
- `keel/tests/test_prod_observe.py` (new; 398 lines, 13 tests)
- `PROD-OBSERVABILITY-EVIDENCE.md` (this file)

No other files were edited. No frontend changes. No push.

---

## 1. Audit scope and findings

Audited: structured logs, event history, correlation/request/task/agent IDs,
error categories, health checks, diagnostics, metrics, resource measurements,
dependency health (DB/provider/worker), audit records, retention and log
rotation. Related local sinks inspected but **not owned**: `keel/redaction.py`
(egress JSONL), `keel/diagnostics.py` (`keel doctor --bundle` ZIP),
`keel/start_health.py` (start-health JSON), `keel/webapp.py` (`/api/health`).

| # | Severity | Confirmed defect | Fix in owned file |
|---|----------|------------------|-------------------|
| F1 | High | No retention/rotation at all: `observability.jsonl` grew without bound (disk-exhaustion risk). | Anchored generation rotation: `DEFAULT_MAX_EVENTS=5000`, `DEFAULT_MAX_ARCHIVES=3`, per-write overrides `max_events`/`max_archives`; oldest archives deleted. |
| F2 | High | Retention anchor could be forged: `verify_chain` trusted a sidecar hash without verifying the archived chain it points to, so editing an archived event went unnoticed. | `_anchor()` now fully verifies the predecessor generation (`_verify` over archive contents with its own first seq/prev hash) before anchoring the active log. |
| F3 | High | Import failures and third-party exception strings were copied verbatim into `health_snapshot().import_error`, dependency results, storage/validation messages and chain errors — a credential in any of those strings would be exported. | Single `_safe_text()` redaction boundary applied to every exception/diagnostic/path string; `health_snapshot` re-redacts `import_error`; HTTP payload carries only booleans/counts. |
| F4 | Medium | `_append()` used one `os.write()` for a whole JSON line; a short write could leave a torn line interleaved with another process. | Write loop over a `memoryview` plus `fsync`. |
| F5 | Medium | No API separated liveness from readiness; a process could be up but not operational with no machine-readable distinction. | `liveness_probe()` (`status="running"`), `readiness_probe()` (`status="ready"` only when chain + modules + dependencies pass), `health_check()` and `health_http_payload()`. |
| F6 | Medium | No structured audit record, dependency health, error categories, resource/metric snapshot or redacted diagnostic export in the backend observability surface. | `record_audit_event` (kind `audit`, request_id linkage), `dependency_health`/`default_dependency_probes`, `metrics_snapshot`, `resource_metrics`, `_error_category`, `export_diagnostics`. |
| F7 | Medium | A corrupt chain was reported by `diagnostic_report` but an empty active log with a rotated anchor still verified as "ok" if the archive was tampered; appends were not refused across generations. | Fail-closed anchor validation propagates `ChainIntegrityError` to `record_event`, `read_events(include_archives=True)` and `verify_chain`; `read_events` self-verifies every retained generation. |

### Red → green evidence

Against the untouched candidate HEAD file (copied into an isolated `PYTHONPATH`
package), the new test file produced **8 failed, 5 passed**:
`test_health_check_distinguishes_running_from_ready`,
`test_readiness_tracks_corrupt_event_chain`,
`test_no_secrets_in_http_response_exceptions_logs_events_and_audit`,
`test_dependency_health_db_provider_worker_and_error_redaction`,
`test_error_categories_and_resource_metrics`,
`test_bounded_retention_rotates_and_preserves_chain`,
`test_corruption_in_archive_fails_closed`,
`test_diagnostic_export_writes_redacted_bundle`.

After the fixes, the required verification command produced **27 passed**
(13 new + 14 existing). Related suites also pass: `test_diagnostics.py`,
`test_redaction.py`, `test_start_health.py`, `test_release_no_secrets.py`
— **20 passed**.

---

## 2. Tests added (`keel/tests/test_prod_observe.py`)

Real JSONL bytes, real threads and real subprocesses are used throughout; no
internal function is mocked except one injected import failure whose only
purpose is to put a credential into an exception message.

- **Health distinction**: `liveness_probe` is `running` even when readiness is
  false; a broken dependency and an unimportable module flip readiness to
  `running`; a corrupt chain flips `checks.chain_ok` to false.
- **No secrets**: multi-word secret (`api_key = '…'`), `Bearer …` token and a
  nested secret are asserted absent from exceptions, HTTP payload, raw log,
  events, audit records, diagnostics, health snapshots and exported bundle.
  Audit events carry `action/actor/outcome/request_id` and a `correlation_id`.
- **Bounded retention**: 20 writes with `max_events=5, max_archives=2` leave
  ≤5 active lines and ≤2 archives; retained history is contiguous and
  verifiable; the next event continues the global seq and `prev_hash`.
- **Diagnostic export**: `export_diagnostics` writes a JSON bundle at the
  caller-chosen path with format/health/diagnostics/metrics sections and no
  credentials.
- **Cross-process integrity**: four real subprocesses write 40 concurrent
  events; all 40 seqs are contiguous 1–40 with 40 unique correlation IDs and
  one unbroken chain. A post-corruption subprocess append exits non-zero with
  `ChainIntegrityError` and leaves the log byte-identical.
- **Concurrent load**: 30 mixed `record_event`/`verify_chain`/
  `diagnostic_report` calls across 12 threads; final chain ok, 10 events, no
  torn lines or leaked secrets.
- **After corruption**: `verify_chain` false, `diagnostic_report` reports
  `chain_status="corrupt"`, `read_events` and `record_event` raise
  `ChainIntegrityError`, and no bytes are appended; the same is proven for a
  corrupted rotated archive.

---

## 3. Log locations and retention policy

**Locations** (all under the caller-supplied `state_root`):

| Path | Purpose |
|------|---------|
| `observability.jsonl` | Active append-only, hash-chained JSONL events (0600). |
| `observability.jsonl.<N>` | Rotated generation archives (ascending N, bounded count). |
| `observability.state.json` | Retention anchor: generation, `base_seq`, `base_hash`, per-generation first/last seq and hashes. |
| `observability.jsonl.lock` | Transient exclusive-create lock (PID + timestamp marker) for cross-process writers. |
| `egress.jsonl` | *External sink* (`keel/redaction.py`): provider egress metadata, redaction counts. |
| `keel doctor --bundle` ZIP | *External sink* (`keel/diagnostics.py`): user-controlled redacted diagnostics bundle. |
| `start-health.json` | *External sink* (`keel/start_health.py`, path overridable via `KEEL_START_HEALTH_FILE`): rollback counter. |

**Retention policy — PROPOSED** (no owner-defined policy was found in the
repository docs; these values need product sign-off):

- Active log capped at **5,000 events** (`DEFAULT_MAX_EVENTS`); the write that
  would exceed the cap is still recorded, then the generation is archived.
- Keep the newest **3 generations** (`DEFAULT_MAX_ARCHIVES`); older archives
  and their metadata entries are deleted on rotation. Minimum one archive is
  retained so the anchor can always be tied to a verified chain.
- No time-based expiry, compression or external shipping in this change
  (Keel is local-only by design; no mandatory telemetry).
- Errors surfaced in `diagnostic_report.recent_errors` are capped at 20.
- Files are created with `0o600` where the OS honours it.
- Callers may tighten both bounds per write for tests or constrained installs.

**Monitoring targets**

| Signal | Target / alert condition |
|--------|--------------------------|
| `verify_chain().ok`, `diagnostic_report().chain_status` | must be `ok`; alert on `corrupt` (hash/link tampering or truncated log). |
| `health_check().status` | `ready` in normal operation; `running` = live but not ready (import/dependency/chain failure). |
| `health_http_payload().dependencies` | all `ok`; watch `database`, `provider`, `worker`, `event_log`. |
| `metrics_snapshot().error_count`, `error_categories` | baseline and alert on sustained growth; categories from `data.error_category`/`data.category`, else `unclassified`. |
| `metrics_snapshot().audit_count` | audit trail growth / unexpected silence. |
| `retention.active_events`, `retention.archive_count`, `retention.generation` | active ≤ cap, archives ≤ cap, generation advancing (rotation working). |
| `resources.max_rss_kb`, `resources.thread_count` | memory/thread growth trends (`rss_source="unavailable"` on Windows). |
| `recent_error_count` | bounded at 20; a full window indicates repeated failures. |

---

## 4. Integration notes and gaps

- `health_http_payload()` is a drop-in JSON body for `/api/health` or a new
  `/api/ready`; `keel/webapp.py` is **not owned**, so the existing endpoint was
  not changed. Wiring remains an integration task.
- No external OTLP/Prometheus export: consistent with the master plan's
  "no mandatory telemetry" rule; all sinks are local.
- The retention anchor is *tamper-evident against accidental/malicious edits
  that break the hash chain*, but the sidecar itself is not signed; full
  authenticity would require a separate trust root (out of scope).
- Cross-process lock staleness uses a 30 s mtime threshold; a legitimate
  writer paused longer than that could have its lock reclaimed (documented
  limitation; no in-process deadlock observed in the 4-process test).
- Time-based retention, archive compression and an owner-approved policy are
  open gaps. `retention.total_events` intentionally counts only the active
  log; archived totals are reported separately.

**Verification command (all pass):**

```
python -c "import sys,pytest; sys.path.insert(0,'keel/src'); raise SystemExit(pytest.main(['-q','keel/tests/test_prod_observe.py','keel/tests/test_backend_observability.py']))"
```

Commit SHA: the SHA of this change on `agent/prod-observe` is reported in the
agent's final report (a commit cannot contain its own SHA).
