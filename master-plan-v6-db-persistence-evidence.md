# Master Plan v6 — Database & Persistence Hardening Evidence

Agent 47 (branch `agent/f-db-persistence`, worktree
`C:\Users\Admin\.local\share\opencode\worktree\final\db-persistence`).
Baseline: `463481edb0f325e9250d9dd5bf559ff5f138a55d`.
Commit: this evidence file is part of the final hardening commit on
`agent/f-db-persistence` (see `git log -1`).

## Scope

Owned files edited:

* `keel/src/keel/backups.py`
* `keel/src/keel/events.py` (persistence helpers added; event construction API untouched)
* `keel/tests/test_db_persistence_hardening.py` (new)

`keel/src/keel/session.py` was audited but **not modified**: it contains no
database helpers (only the in-memory turn loop, `Persist` tool-result hook and
`TranscriptWriter` usage). Changing session behaviour was explicitly out of
scope.

Test environment note: the interpreter has an editable install of `keel`
pointing at the main checkout, so all commands below set
`PYTHONPATH=<worktree>\keel\src` to guarantee the worktree code is under test.

---

## Defect 1 — backup creation was not atomic

**Location:** `backups.py::create_backup` (baseline lines 74–76:
`target.write_text(json.dumps(doc), ...)`).

**Failure mode:** the encrypted backup document was written in place. A crash
or I/O error part-way through left a truncated file at the final backup path.
That file still looks like a backup path to the user but cannot be restored —
the previous good backup is destroyed at the first byte of a failed write.

**Reproduction (failing test):**
`test_create_backup_is_atomic_on_interrupted_write` pre-creates a valid
old backup, then monkeypatches the write path / rename to raise after a
partial write. On baseline the target contains
`b'{"format":"keel-backup-v1","trunc'` instead of the original bytes.

**Fix:** `create_backup` now serialises the document once and calls
`_atomic_write(target, data)`: write to a sibling hidden `.tmp` file, `flush` +
`fsync`, then `os.replace` onto the destination. Exceptions unlink the staging
file. The last good backup survives byte-for-byte; no half-written backup and
no temp litter remain.

## Defect 2 — restore clobbered newer state without a guard

**Location:** `backups.py::restore_backup` (baseline lines 96–109).

**Failure mode:** every archived file was unconditionally written over the
destination. Restoring an old backup over a directory where a human had since
edited a file silently destroyed the newer state.

**Reproduction (failing test):**
`test_restore_refuses_to_clobber_newer_state` backs up `config.txt`, restores
it, edits the restored file, pushes its mtime one hour forward, then restores
the same backup again. Baseline overwrites `"newer value"` with `"old value"`
without complaint.

**Fix:** `create_backup` now records each file's `mtime` in the manifest;
`restore_backup` compares the on-disk file with the archived bytes and, when
they differ, refuses to replace a file whose mtime is newer than the archived
mtime (`BackupError: refusing to overwrite newer file: ... (pass
overwrite=True to force)`). Explicit recovery is still possible via the new
keyword-only `overwrite=True`. Backups without timestamps (legacy) keep the
old permissive behaviour. Identical content is never treated as a conflict.

## Defect 3 — restore validated and wrote one file at a time (partial restores)

**Location:** `backups.py::restore_backup` (baseline verified each member
*inside* the write loop, after `destination.mkdir()`).

**Failure mode:** a backup whose later member failed the SHA-256 check left
earlier members already written into the destination. There was also no check
that all manifest entries were present in the tar payload, so a truncated
archive could "restore successfully" with missing files.

**Reproduction (failing tests):**
`test_restore_validates_entire_archive_before_writing` builds a validly
encrypted backup whose second member's manifest hash is wrong — baseline
writes the first file before failing. `test_restore_rejects_manifest_missing_members`
builds an archive with a member absent from the manifest — baseline reports a
generic integrity error rather than a manifest mismatch.

**Fix:** restore is now three phases: (1) decrypt, validate *every* member
name and hash, and compare the member set against the manifest; (2) apply the
newer-state guard; (3) only then create the destination and write files, each
through `_atomic_write`. Any validation error leaves the destination untouched.

## Defect 4 — archive member names were not path-checked

**Location:** `backups.py::restore_backup` (baseline wrote
`destination / member.name` directly).

**Failure mode:** a backup crafted with a member named `../escaped.txt` (and
a matching manifest hash, so it passes the integrity check) writes outside
the requested destination directory.

**Reproduction (failing test):** `test_restore_rejects_path_traversal`
builds such a backup with the test's `_build_backup` helper. Baseline creates
`<tmp>/escaped.txt` outside `<tmp>/destination`.

**Fix:** `_safe_member_name` rejects absolute paths, backslashes, drive
colons, NULs, whitespace-padded names and any `..` or empty path component —
for both manifest entries and tar members.

## Defect 5 — persisted event logs had no integrity check

**Location:** `keel/events.py` (baseline had only `iter_lines`, no persistence
helpers; the JSONL transcript written by `keel.transcript.TranscriptWriter`
was only checked for JSON parseability).

**Failure mode:** tampering with a single byte of an event, or truncating the
tail of the log, was silently accepted on read: `read_entries` yielded the
forged/truncated history as if authentic. There was also no protection for
interleaved appends from concurrent writers.

**Reproduction (failing tests):** `test_event_log_detects_tampering`,
`test_event_log_detects_truncation`, `test_concurrent_event_appends_keep_a_valid_chain`,
`test_event_log_chain_missing_is_detected`. On baseline all four fail with
`ImportError` because no integrity-aware persistence API existed.

**Fix (additive — existing event dicts and `iter_lines` are unchanged):**

* `write_event_log(path, events)` — writes plain stream-json JSONL plus a
  sibling `<path>.chain` with one SHA-256 per line. Each digest commits to
  the event, its 1-based sequence number, and the previous digest
  (genesis = 64 zeroes). Both files are written atomically.
* `append_event(path, event)` — appends one event and one chain link under a
  module-level re-entrant lock, with `flush` + `fsync`; refuses to append if
  the chain is missing or out of sync.
* `read_event_log(path, verify=True)` — verifies line count, every digest and
  chain linkage; raises `EventLogError` on alteration, truncation, deletion,
  unparseable lines or a missing chain. `verify=False` gives legacy parse-only
  behaviour.
* `verify_event_log(path)` — boolean convenience wrapper.

The JSONL payload stays compatible with `keel.transcript.read_entries`.

## Audit items with no defect found

* `keel.fleet.db._migrate` — `test_legacy_db_migration_preserves_existing_rows`
  upgrades a version-1 database carrying a bot and a message row to
  `SCHEMA_VERSION` (11) and verifies both rows are intact. No data loss
  observed.
* `keel.resilience.db_backup` uses `sqlite3.Connection.backup`, which produces
  a consistent online copy (not a `VACUUM INTO`). The plan document
  `Keel_Plan_v5_Addendum_2_More_Features.md` (C8.7) claims `VACUUM INTO`.
  This is a documentation/implementation mismatch **outside the files I own**
  (`keel/src/keel/resilience.py`) — referred to the lead. Test
  `test_resilience.py` passes unchanged; no behavioural defect demonstrated.

---

## Test commands and results

All from `<worktree>\keel`, with
`$env:PYTHONPATH = "<worktree>\keel\src"`.

Baseline (before fixes), new regression file:

```
python -m pytest tests/test_db_persistence_hardening.py -q
9 failed in 4.68s
```

After fixes:

```
python -m pytest tests/test_db_persistence_hardening.py -q
11 passed in 6.14s

python -m pytest tests/test_backups.py tests/test_backup_endpoints.py \
  tests/test_db_persistence_hardening.py tests/test_concurrency_recovery.py \
  tests/test_vertical_slice.py tests/test_resilience.py -q
32 passed in 11.55s

python -m pytest tests/test_e2e_milestone_6b.py tests/test_hooks.py \
  tests/test_session_endpoints.py tests/test_webapp.py \
  tests/test_reliability_e2e.py -q
44 passed in 89.27s (0:01:29)
```

`python -m ruff check ...` was unavailable (`No module named ruff`); no lint
result is claimed.

---

## Follow-up: Windows `os.replace` sharing violation (re-committed)

**Reported failure (integrated branch, Windows 10):**
`tests/test_db_persistence_hardening.py::test_concurrent_backup_creates_leave_one_valid_backup`
raised `PermissionError: [WinError 5] Access is denied: '<tmp>/.shared-backup.json.<rand>.tmp' -> '<tmp>/shared-backup.json'`
at `backups.py:52 os.replace(tmp, target)`. On Windows another thread holding
the destination open can transiently block the rename.

**Fix:** both atomic-write paths (`backups.py::_atomic_write` and
`events.py::_atomic_text`) now call a bounded `_replace_with_retry(tmp, target)`
helper: 5 attempts, 0.02 s backoff between attempts, retrying only
`PermissionError`/`OSError` with `winerror` 5 or 32 (or no winerror, e.g.
POSIX). Other OS errors are raised immediately; after the final failure the
original exception is re-raised. The staging file is only unlinked in the
outer `except`, so the destination stays byte-for-byte intact for the whole
retry window and no temp files are left behind.

Checked `keel/src/keel/release/common.py` — it contains no `os.replace` /
`mkstemp` / atomic-write helper, so no change was needed there.

**New deterministic regressions:** `test_atomic_write_retries_transient_windows_sharing_violation`
(WinError 5 twice, then success), `test_atomic_write_rethrows_after_retries_without_clobbering`
(persistent WinError 5: old backup intact, no temp leftovers), and
`test_event_log_write_retries_transient_windows_sharing_violation` (same for
the event-log/chain writer).

**Verification (Windows worktree, exact lead command):**

```
python -c "import sys,pytest; sys.path.insert(0,'keel/src'); raise SystemExit(pytest.main(['-q','keel/tests/test_db_persistence_hardening.py']))"
14 passed in 5.14s

python -c "import sys,pytest; sys.path.insert(0,'keel/src'); raise SystemExit(pytest.main(['-q','keel/tests/test_backups.py','keel/tests/test_backup_endpoints.py','keel/tests/test_concurrency_recovery.py','keel/tests/test_resilience.py']))"
14 passed in 7.79s
```

The original concurrency failure was **not reproducible in my worktree** (5
consecutive runs of that single test all passed), so the defensive retry was
applied as specified rather than relying on timing. `pytest-repeat` is not
installed (`--count` unrecognized), so repetition used 5 separate pytest
processes instead.
