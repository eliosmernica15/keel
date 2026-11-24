# Master Plan v6 — Recovery & Reliability Evidence (Agent 48)

- Branch: `agent/f-recovery`
- Baseline: `463481e` (`Merge product defect fixes: DOCX lossless roundtrip, codemod attribute rename, workflow fake-success`)
- Worktree: `C:\Users\Admin\.local\share\opencode\worktree\final\recovery`
- Files owned: `resilience.py`, `message_state.py`, `circuit_breaker.py`, `trash.py`, `tests/test_recovery_hardening.py`, this document.

## Environment note

The editable `keel-harness` install on this machine points at
`C:\Users\Admin\Desktop\Claude clone\keel\src`, so all test commands below set
`PYTHONPATH` to the worktree copy explicitly and verify the imported module path:

```
PYTHONPATH=C:\Users\Admin\.local\share\opencode\worktree\final\recovery\keel\src
python -c "import keel; print(keel.__file__)"
-> ...\worktree\final\recovery\keel\src\keel\__init__.py
```

Without that override the tests would silently exercise the unmodified main checkout.

---

## Defects found and fixed

### D1 — `CanaryFiles.add()` wrote live state non-atomically (crash erased all canaries)

- **Reproduction:** `test_canary_add_survives_crash_mid_write` registers a canary, then
  monkeypatches `Path.write_text` so a write to `canary-files.json` leaves a truncated
  document and raises (simulated power loss). After the "restart", `_load()` sees torn
  JSON, returns `[]`, and both the old and the new canary are gone.
- **Root cause:** `add()` called `self.path.write_text(...)` directly on the published
  file; truncating it is the first step of the write, so any interruption destroys the
  previous state.
- **Fix:** added `_atomic_write()` (same-directory random temp file + `os.replace`,
  temp cleaned in `finally`); `add()` now publishes through it. The loader's existing
  tolerance of torn JSON is retained (verified by `test_canary_loader_tolerates_torn_json`).
- **Before:** `11 failed, 2 passed` (whole new regression file; this test failed with
  `assert False != True` on `canaries.touches(...)`).
- **After:** passes.

### D2 — `ContentStore.put()` permanently wedged a corrupt blob after a partial write

- **Reproduction:** `test_content_store_repairs_blob_left_by_crash` patches
  `Path.write_bytes` for the digest-named target to write 10 bytes then raise.
  On retry, `put()` saw `target.exists()` and skipped the write, so `get()` returned
  `None` forever. `test_content_store_detects_and_repairs_corrupt_existing_blob`
  plants wrong bytes at the digest path directly.
- **Root cause:** existence check used as a proxy for integrity; non-atomic writes left
  corrupted content-addressable blobs that were then trusted permanently.
- **Fix:** `put()` now hashes any existing blob and rewrites it on mismatch; all writes
  go through `_atomic_write()`, so a crash cannot leave a partial blob at the final path.
- **After:** both tests pass.

### D3 — torn final JSONL line swallowed the next message-state append

- **Reproduction:** `test_torn_last_line_does_not_swallow_next_append` leaves
  `{"id":"crashed","state":"queued"` with no newline, then calls `advance(id, "sent")`.
  The new record was concatenated onto the partial line, producing one invalid JSON
  line that `_records()` discarded; `state()` stayed `"queued"`.
- **Root cause:** `_append()` used plain `"a"` mode without checking whether the
  previous write ended in a newline, and never flushed/fsynced durable state.
- **Fix:** `_append()` opens in `"a+b"`, checks the last byte and inserts a newline to
  terminate a torn tail before appending the new record, then `flush()` + `os.fsync()`.
- **After:** passes; history is exactly `["queued", "sent"]`.

### D4 — corrupt JSONL scalars crashed the message-state loader

- **Reproduction:** `test_message_state_ignores_non_object_records` appends `42` and
  `"not a record"` lines; `state()` raised `AttributeError: 'int' object has no
  attribute 'get'`.
- **Fix:** `_records()` only accepts decoded JSON objects, skipping scalars/lists.
- **After:** passes. `test_message_state_transition_graph_has_no_state_skips` also
  confirms no legal direct transition skips a delivery stage (this one passed before
  and after — the existing graph was correct).

### D5 — interrupted half-open probe wedged the circuit breaker forever

- **Reproduction:** `test_interrupted_half_open_probe_does_not_wedge_breaker` opens the
  breaker, allows a probe, then never records an outcome (aborted task/crash).
  `allow()` kept returning `False` indefinitely because `_half_open_inflight` stayed at 1.
- **Root cause:** no timeout/expiry for probe bookkeeping.
- **Fix:** added `_probe_started_at` and `_expire_stale_probes()`; when a probe batch
  has been outstanding for at least `recovery_timeout`, its inflight slots are
  released and a fresh probe is admitted.
- **After:** passes; a subsequent success closes the breaker.

### D6 — a failing half-open probe was silently erased by a later success

- **Reproduction:** `test_single_failure_during_parallel_probes_keeps_breaker_open`
  (`half_open_max=2`) sends two probes; probe A fails (window restarts) and probe B
  reports success late. `record_success()` unconditionally closed the breaker.
- **Root cause:** `record_success()` only checked `_opened_at` truthiness, not whether
  the current half-open window had already seen a failure or other outstanding probes.
- **Fix:** added `_half_open_failed`; a success closes the breaker only when inflight
  reaches zero and no probe in the window failed. Probe-failure state is reset when a
  fresh probe batch starts.
- **After:** passes. Existing breaker tests (including the model-client fail-fast test)
  still pass unchanged.

### D7 — a trashed `.json` file could not be restored

- **Reproduction:** `test_restore_json_named_file` moves `config.json` to trash;
  `restore()` raised `TrashError: trash item missing` with `KeyError: 'id'` at the
  listing layer because candidate selection excluded every path whose suffix was
  `.json` — which excluded the actual data blob.
- **Fix:** candidates are now matched by the `{trash_id}-*` name pattern and explicit
  exclusion of the metadata path, not by suffix. Metadata is published atomically
  (`_write_meta`).
- **After:** passes; file content round-trips.

### D8 — trash retention was never enforced (unbounded growth)

- **Reproduction:** `test_trash_retention_purges_expired_items` backdates a metadata
  timestamp to 2000 and calls `list_items()` — the item was still listed and both
  metadata and blob remained on disk. `test_trash_retention_enforces_max_items` with
  `KEEL_TRASH_MAX_ITEMS=2` created 5 items; all 5 were listed.
- **Fix:** added `purge_expired()` enforcing `KEEL_TRASH_RETENTION_DAYS` (default 30)
  and `KEEL_TRASH_MAX_ITEMS` (default 100), deleting both metadata and data blobs.
  Called from `move_to_trash()` and `list_items()`. Only well-formed docs with `id`
  and `original_path` are considered; unrelated files such as `redo-last.json` are
  never touched.
- **After:** both tests pass; the oldest items are the ones discarded.

### D9 — one torn metadata file broke all trash listing/undo

- **Reproduction:** `test_trash_list_ignores_torn_metadata` plants `torn.json` containing
  `{"id": "tor`; `list_items()` raised `json.decoder.JSONDecodeError`.
- **Fix:** `_load_meta()` returns `None` for unreadable/invalid/foreign JSON;
  `list_items()` skips those entries. Metadata writes are atomic, and `restore()`
  validates metadata before use.
- **After:** passes.

---

## Test results (exact commands and outcomes)

All commands run from `...\worktree\final\recovery\keel` with the worktree `PYTHONPATH`
shown above.

### Red phase — new regressions against unmodified baseline

```
python -m pytest tests/test_recovery_hardening.py -q --tb=line
11 failed, 2 passed in 2.06s
```

(2 passing baseline checks: torn canary JSON is tolerated by the loader; the
transition graph already forbade skips.)

### Green phase — new regressions after fixes

```
python -m pytest tests/test_recovery_hardening.py -q --tb=short
13 passed in 2.15s

python -m pytest tests/test_recovery_hardening.py tests/test_resilience.py \
  tests/test_circuit_breaker.py tests/test_message_state.py tests/test_trash.py -q
27 passed in 4.77s
```

### Required targeted + related existing suites

```
python -m pytest tests/test_resilience.py tests/test_recovery_hardening.py \
  tests/test_circuit_breaker.py tests/test_message_state.py tests/test_trash.py \
  tests/test_dry_run.py tests/test_concurrency_recovery.py tests/test_slash_commands.py \
  tests/test_e2e_operations.py tests/test_workflows_e2e.py -q --tb=short
69 passed in 24.83s
```

Includes `test_resilience*`, `test_circuit_breaker.py`, `test_dry_run.py`,
`test_concurrency_recovery.py`, plus adjacent trash/message/workflow suites.

### Full suite

```
python -m pytest -q --tb=short
7 failed, 1315 passed, 49 skipped in 544.37s
```

The 7 failures are not caused by these changes. Six were reproduced identically with
all four tracked source files stashed back to baseline:

- `test_distribution_package.py::test_release_manifest_has_policy_fields`
- `test_distribution_package.py::test_checksums_file_matches_manifest_artifacts`
- `test_gap_closure.py::test_c12_package_manager_manifests`
- `test_gap_closure.py::test_c122_airgap_bundle_and_verification`
- `test_plan_index.py::test_authoritative_source_hashes_unchanged`
- `test_release_integrity.py::test_integrity_cli_on_real_artifacts`

Cause: generated release artifacts (`keel/release/RELEASE-MANIFEST.json`,
`RELEASE-SHA256SUMS.txt`, etc.) are absent from this checkout, and one plan hash is
stale. The seventh, `test_compat_runtime.py::test_tool_requires_approval_then_approved_runs`,
passed at baseline in the same 7-test subset and passes with the fixes both alone
(`1 passed in 2.12s`) and in that subset (`6 failed, 1 passed`); it is an
order-dependent flake in the full-suite run, unrelated to the four modules owned here.

No existing test was skipped or weakened; all new tests use real functions and temp dirs.

## Commit

Reported in the final agent response.
