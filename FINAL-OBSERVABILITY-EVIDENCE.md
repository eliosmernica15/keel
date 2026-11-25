# Final verification evidence — observability integration and operational safety

**Branch:** `agent/final-observe2` · **Completion HEAD:** `35fb2b8` ·
**Worktree:** `C:\Users\Admin\.local\share\opencode\worktree\final\observe2`

**Files owned / changed**

- `keel/src/keel/backend_observability.py` — atomic-write cleanup, real provider probe,
  no-probe honesty guard
- `keel/src/keel/webapp.py` — `/api/health` and `/api/ready` only: real `providers`
  probe plus `initialized`/`chain_status` in the payload (no workflow endpoints touched)
- `keel/src/keel/diagnostics.py` — broader credential-name masking in `keel doctor --bundle`
- `keel/tests/test_final_observe.py` — new, 20 tests
- `FINAL-OBSERVABILITY-EVIDENCE.md` — this file

No frontend changes. No push. No external monitoring service is required or introduced.

---

## 1. Confirmed defects and fixes

| # | Severity | Confirmed defect (reproduced against `35fb2b8`) | Fix in owned file |
|---|----------|--------------------------------------------------|-------------------|
| D1 | Medium | `_atomic_write()` left `<target>.tmp` behind on a disk-full / short write or a failed `os.replace`. Cleanup under storage failure was incomplete. | Write loop now closes the fd and `_unlink_with_retry()`s the temporary on *any* exception and on a failed replace; successful writes still use `os.replace` (verified: old bytes intact, no `.tmp` debris). |
| D2 | Medium | `default_dependency_probes()['provider']` was `importlib.util.find_spec(...) is not None` — a module-presence flag, not an executed probe, while the docstring claimed a real probe. | Probe now imports `keel.providers.registry`, calls `list_providers()` and `build_adapter()` for the first provider with a placeholder key. No network, no credential required. |
| D3 | Medium | `dependency_health({})` returned `healthy=True` from `all([])` — readiness could be claimed with zero dependencies checked. | Empty probe set returns `healthy=False`, `dependency_count=0` and an explicit `error`; `health_check(..., dependencies={})` is live but not ready. |
| D4 | Medium | `/api/health` and `/api/ready` executed only DB/events/worker probes; the provider subsystem was invisible. The payload also omitted `initialized`/`chain_status`. | Added a real `providers()` probe to `webapp._readiness_dependencies()` (registry enumeration + adapter construction, no network/keys) and exposed `initialized` and `chain_status` in `_health_payload()`. A failing provider probe flips `/api/ready` to **503** and `/api/health` to `ready:false` while `ok:true` (liveness) stays truthful. |
| D5 | Low | `diagnostics.collect()` masked only `KEY/TOKEN/SECRET/PASSWORD/CREDENTIAL` names; `KEEL_PASSPHRASE`, `KEEL_AUTHORIZATION`, `KEEL_PRIVATE_KEY` style names could carry raw values into `keel doctor --bundle`. | `SENSITIVE` extended with `PASSPHRASE`, `PRIVATE`, `APIKEY`, `AUTHORIZATION`, `COOKIE`. Verified on the generated ZIP, not just `collect()`. |

Items that were **verified correct with no defect found**: structured event schema and
per-event UUID correlation IDs; audit `action/actor/outcome/request_id` linkage;
liveness vs readiness distinction; error categories and bounded `recent_errors`;
metrics and resource measurement; `export_diagnostics` redaction; anchored hash-chain
rotation, forensic preservation of retired generations, fail-closed reads/appends,
configurable caps (`max_events`, `max_archives`) and cross-process locking.

### Red → green evidence

With the three fixed source files checked out back to `35fb2b8` and only the new test
file present:

```
$ python -m pytest tests/test_final_observe.py -q
4 failed, 16 passed in 16.68s
FAILED tests/test_final_observe.py::test_dependency_health_without_probes_is_not_healthy
FAILED tests/test_final_observe.py::test_webapp_health_and_ready_report_real_dependencies
FAILED tests/test_final_observe.py::test_diagnostics_bundle_masks_secret_named_environment_values
FAILED tests/test_final_observe.py::test_atomic_write_is_replacement_and_cleans_up_on_failure
```

After restoring the fixes:

```
$ python -m pytest tests/test_final_observe.py -q
20 passed in 14.60s
```

The `test_default_provider_probe_is_a_real_executable_probe` regression case also
monkeypatches `registry.list_providers` to return `[]` and requires the probe to
report `error`, so a return to the old `find_spec` check would be caught.

---

## 2. Final verification (clean HOME)

The editable install in this environment points at a different clone, so every
command pins `PYTHONPATH` to this worktree and uses a fresh HOME / state root.
PowerShell:

```powershell
$clean = "C:\Users\Admin\AppData\Local\Temp\opencode\clean-home-observe"
if (Test-Path $clean) { Remove-Item -Recurse -Force $clean }
New-Item -ItemType Directory -Path $clean -Force | Out-Null
$env:PYTHONPATH = "C:\Users\Admin\.local\share\opencode\worktree\final\observe2\keel\src"
$env:HOME = $clean
$env:USERPROFILE = $clean
$env:KEEL_STATE_DIR = "$clean\.keel"
python -c "import os,keel; print('HOME=',os.environ['HOME']); print('keel=',keel.__file__); print('STATE=',os.environ['KEEL_STATE_DIR'])"
python -m pytest tests/test_final_observe.py tests/test_backend_observability.py tests/test_prod_observe.py tests/test_start_health.py tests/test_webapp.py -q
```

Output (sanity + result):

```
HOME= C:\Users\Admin\AppData\Local\Temp\opencode\clean-home-observe
keel= C:\Users\Admin\.local\share\opencode\worktree\final\observe2\keel\src\keel\__init__.py
STATE= C:\Users\Admin\AppData\Local\Temp\opencode\clean-home-observe\.keel
.................................................................        [100%]
65 passed in 52.64s
```

**Verdict: PASS** — 20 new + 14 `test_backend_observability` + 13 `test_prod_observe`
+ 3 `test_start_health` + 15 `test_webapp` tests, all in a clean HOME.

Related suites (same pins):

```
$ python -m pytest tests/test_diagnostics.py tests/test_redaction.py -q
...                                                                          [100%]
13 passed
```

Combined earlier run of the required suites plus these two related suites:

```
$ python -m pytest tests/test_backend_observability.py tests/test_prod_observe.py tests/test_start_health.py tests/test_webapp.py tests/test_diagnostics.py tests/test_redaction.py -q
58 passed in 50.88s
```

Full-suite regression:

```
$ python -m pytest -q
........................................................................ [ 99%]
...............................                                  [100%]
4630 passed, 54 skipped, 3707 subtests passed in 750.71s (0:12:30)
```

**Verdict: PASS** — no regression anywhere in the full suite (the 20 new tests are
included in the 4630).

---

## 3. Verification by task item

### 3.1 Structured logs, correlation IDs, health/readiness, categories, metrics,
audit, diagnostic export — **PASS**

- `test_structured_event_and_audit_carry_correlation_and_identity`: every stored event
  has `seq/ts/kind/session_id/task_id/agent_id/feature_id/module/correlation_id/data/
  prev_hash/hash`; 32-hex correlation IDs; audit records carry `action`, `actor`,
  `outcome`, `request_id` linking to the originating correlation ID and their own
  distinct correlation ID; chain verifies.
- `test_high_volume_concurrent_writes_keep_unique_ids_and_full_history`: 150 writes
  across 12 threads → 150 unique correlation IDs, contiguous seq 1–150 across
  forensic + hot archives, chain and forensic verification both `ok`.
- `test_health_http_payload_reports_every_real_dependency`: all four probes are
  *executed* (recording set equals `database/events/workers/providers`) and reported by
  name; `ready=True`, `status="ready"`.
- `test_metrics_error_categories_and_recent_error_window_are_bounded`: 25 errors split
  into `{"database": 13, "provider": 12}`, 1 audit event, `recent_error_count<=20`.
- `test_webapp_health_and_ready_report_real_dependencies`: real local HTTP server;
  `/api/health` returns 200 with `ok/ready/status/initialized/chain_status/
  dependencies/correlation_id` and all four dependency names; `/api/ready` returns
  200 `{"ready": true, "status": "ready"}` on a healthy fresh root.

### 3.2 Redaction of secrets / personal data — **PASS**

`test_natural_language_secrets_are_redacted_in_every_channel` injects
`"The password is Harbor Seal42 Tango Mike"` and
`"The passphrase was green lantern delta 99"` into an event, an audit detail and an
import-failure exception, then asserts both secret values are absent from the raw
JSONL bytes, read events, audit record, diagnostic report, health snapshot, HTTP
payload and exported JSON bundle (`[REDACTED]` present).

`test_bearer_token_is_redacted_in_exception_response_logs_and_audit` does the same
for `Bearer abcdef1234567890XYZ` in a dependency exception, an event value, an audit
detail and the persisted bytes.

`test_diagnostics_bundle_masks_secret_named_environment_values` puts credentials in
`KEEL_PASSPHRASE_*`, `KEEL_AUTHORIZATION_*` and `KEEL_PRIVATE_KEY_*` environment
variables and asserts they are absent from both `collect()` and the bytes of the
generated ZIP's `diagnostics.json`.

`test_health_payload_omits_paths_and_raw_import_errors` confirms the HTTP body carries
no state-root path, raw import error or exception type.

### 3.3 Bounded retention, rotation, evidence preservation, atomic writes — **PASS**

- `test_forensic_archives_preserve_hash_chain_and_full_history`: 40 writes with
  `max_events=5, max_archives=2` → forensic verification `ok`, full seq 1–40
  recoverable by concatenating `read_forensic_archives()` and
  `read_events(include_archives=True)`, hot window bounded, active chain `ok`.
- `test_tampered_forensic_archive_fails_closed`: editing one forensic byte makes
  `verify_forensic_archives()['ok']` false and `read_forensic_archives()` raise
  `ChainIntegrityError`.
- `test_rotation_failure_preserves_evidence_and_raises_typed_error`: with a file placed
  at the forensic-directory path, rotation raises `ObservabilityStorageError`;
  both hot archives, the blocking file and all active bytes are unchanged and the
  chain still verifies — no silent destruction of security evidence.
- `test_atomic_write_is_replacement_and_cleans_up_on_failure`: replace semantics
  verified, and a simulated disk-full leaves neither a partial target nor a `.tmp`.
- `test_tightest_configurable_caps_still_verify` (`max_events=1, max_archives=1`) and
  `test_corrupt_retention_state_fails_closed` cover cap extremes and sidecar tampering.

### 3.4 High-volume / storage failures / no mandatory external service — **PASS**

The 150-thread and 40-generation tests above exercise sustained rotation. A separate
600-write probe completed in 7.59 s with `verify_chain.ok=True`, `last_seq=600`,
8 forensic archives containing 408 events, 192 hot events, and a contiguous 1–600
sequence with no loss. Storage failures produce typed errors and preserve evidence
(D1 fix and rotation test). `test_no_mandatory_external_monitoring_service` asserts
the observability and diagnostics sources contain no Prometheus/OpenTelemetry/
Datadog/Sentry/StatsD/HTTP-post dependency; the health probes import the local
provider registry and build an adapter object without any network call or required
API key.

---

## 4. Limitations (not silently papered over)

- The retention sidecar is tamper-*evident* through hash linkage but not signed; a
  rewrite of both the log and sidecar with recomputed hashes would need a separate
  trust root (out of scope, unchanged).
- A crash between `_rotate()` truncating the active log and persisting the new state
  leaves a detectable chain discontinuity (fail-closed), not a silent loss; atomic
  two-file replacement would be needed for crash-consistent rotation.
- The central `keel/redaction.py` natural-language pattern covers
  `password/passphrase/secret is|was …`. A bare natural-language **PIN**
  (`"the PIN is 4821"`) is still not detected there; that file is not owned by this
  agent. Avoid placing such values in event data until the central vocabulary is
  extended. Assignment-style secrets (`api_key = …`, `pin = …`) and Bearer tokens
  *are* redacted.
- `default_dependency_probes()['database']` executes `SELECT 1` against an in-memory
  SQLite database; it proves SQLite is usable, not that the application's Fleet DB
  is healthy. The **webapp** readiness endpoint uses the real Fleet DB file probe
  (`PRAGMA quick_check`), which is the readiness path operators should watch.
- `keel/tests/test_webapp.py::test_run_streams_events_and_done_marker` timed out when
  run with the machine's default HOME (stale `.keel` state); with the clean HOME /
  `KEEL_STATE_DIR` used above, all 15 webapp tests pass. This is a state-isolation
  issue, not a health-endpoint change.
- `max_rss_kb` reports `"rss_source": "unavailable"` on Windows; thread count and all
  counters remain available.
