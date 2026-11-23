# Addendum 5 — Transcript / history contracts (Y2.x P0): implementation evidence

Branch: `agent/a5-transcripts` (worktree `.../worktree/addenda/a5-transcripts`)
Baseline: `9201f2a`, read-only.
Source of requirements: `PLAN-INDEX.json` → `features[]`, every **not_started P0**
Y2.x row: Y2.1, Y2.2, Y2.3, Y2.4, Y2.5, Y2.6, Y2.7, Y2.8, Y2.14, Y2.20
(10 items, milestones M3/M4/M15/M16).  The six explicitly requested IDs
(Y2.1, Y2.2, Y2.3, Y2.4, Y2.14, Y2.20) plus the four remaining not_started P0
rows are all implemented in one additive module.

This workstream is **additive**. No existing source file or test was edited:
`keel/transcript.py`, `keel/session.py`, `keel/pairing.py`, `keel/webapp.py`,
the CLI and every pre-existing test are untouched. The canonical implementation
lives in a new module and is exercised by a new, permanent contract-regression
test file. Integration into the live runtime is a separate lead decision (exact
seams listed at the end).

## Files owned

| File | Purpose |
| --- | --- |
| `keel/src/keel/transcript_contracts.py` | Canonical implementation of all 10 Y2.x contracts (stdlib only, no I/O side effects at import, no network/socket/uuid). |
| `keel/tests/test_transcript_contracts.py` | 39 permanent contract tests, one or more groups per registry ID. |
| `master-plan-v6-transcript-contracts-evidence.md` | This document. |

## Contracts implemented

| ID | Registry requirement | Primary symbols | Tests |
| --- | --- | --- | --- |
| Y2.1 | Append-mostly typed rows: `seq`, `updatedSeq`, `kind`, JSON `body`; streaming reply = same row with higher revision; clients upsert by seq; per-session generation resets the conversation | `RowKind`, `Provenance`, `TranscriptRow`, `TranscriptStore`, `validate_rows`, `validate_append`, `validate_rewrite`, `apply_snapshot` + 3 typed errors | `test_row_kinds_*`, `test_stable_id_*`, `test_upsert_by_seq_*`, `test_generation_reset_*`, `test_append_only_*`, `test_replay_hashes_*` (6) |
| Y2.2 | `model_items` stored separately from UI rows (`llm_items`); UI redaction never corrupts model input; reasoning blobs passed back unchanged; model-visible ⇔ logged | `ModelItem`, `ModelHistory`, `UiRow`, `SplitHistory`, `model_item_from_row`, `split_history`, `reconcile`, `assert_reconciled`, `HistoryReconciliationError` | `test_split_history_*`, `test_ui_redaction_*`, `test_model_visible_iff_*`, `test_reasoning_blob_*` (4) |
| Y2.3 | Last N screenshots inline (N=3 configurable); descriptor + bounded retention; local file refs only; no fabrication | `ScreenshotDescriptor`, `describe_screenshot`, `assert_real_screenshot`, `is_local_ref`, `ScreenshotRing`, `PruneReport`, `DEFAULT_INLINE_SCREENSHOTS` + 3 typed errors | `test_descriptor_is_built_*`, `test_only_local_*`, `test_local_paths_*`, `test_missing_file_*`, `test_ring_keeps_*`, `test_ring_capacity_*` (5 + 7 parametrized local-ref cases) |
| Y2.4 | Orphaned tool-call repair before the next model call; synthetic "interrupted" result; never silently invents success | `ToolCallRef`, `find_orphan_tool_calls`, `synthetic_missing_result`, `repair_orphaned_tool_calls` | `test_find_orphan_*`, `test_repair_appends_*`, `test_repair_is_idempotent_*` (3) |
| Y2.14 | VNC relay hides credentials from the browser; watch mode drops keyboard/pointer/clipboard on the server | `VncCredentials`, `VncRelay`, `VncRelayDescriptor`, `RelayMode`, `VncInputEvent`, `RelaySeam`, `RecordingSeam`, `assert_credential_free` | `test_vnc_descriptor_never_*`, `test_vnc_watch_mode_*`, `test_vnc_descriptor_shape_*` (3) |
| Y2.20 | Bind 127.0.0.1; dev login ignored off-localhost; refuse sign-ups on a public URL until an allowlist is set; emails or `@domain`; least-exposure defaults for transcripts/screenshots | `ExposurePolicy`, `Visibility`, `normalize_allowlist`, `allowlist_matches`, `is_local_host`, `effective_dev_login`, `validate_exposure`, `authorize_signup`, `share_transcripts`, `share_screenshots`, `can_expose`, `env_reference` | `test_exposure_defaults_*`, `test_public_bind_*`, `test_allowlist_*`, `test_signup_refused_*`, `test_sharing_requires_*` (5) |
| Y2.5 | Per-agent serial queue; a user message while a turn pends expires the pending approval | `TurnTicket`, `SerialTurnQueue` | `test_serial_queue_runs_*`, `test_user_message_expires_*` (2) |
| Y2.6 | Persist pending tool calls when approval is needed; resume after the answer, surviving restarts | `PendingTurn`, `PendingTurnFileStore`, `PendingTurnError` | `test_pending_turn_survives_*`, `test_pending_turn_rejects_*` (2) |
| Y2.7 | Allow / Always allow (per-tool policy) / Don't allow (inject a no-retry instruction) | `ApprovalChoice`, `ApprovalCard`, `ApprovalOutcome`, `ApprovalPolicyStore`, `resolve_approval`, `NO_RETRY_INSTRUCTION` | `test_approval_buttons_*` (1) |
| Y2.8 | Read-only classification by explicit manifest flag; name rules only as a warned fallback; meta tools and batches always need approval | `ToolClassification`, `classify_connector_tool`, `WRITE_MARKERS`, `META_MARKERS`, `READ_SLUGS` | `test_connector_tool_classification_*` (1) |

Total: **39 tests**, all passing (3 consecutive runs, 0.80–0.89 s each).
`py_compile` clean on both new Python files.

## Design decisions worth the lead's attention

1. **Identity and revision are separate.** `seq` is assigned once, never reused,
   and is the upsert key. `updated_seq` is a per-session revision counter; a
   streaming reply rewrites the same `id`/`seq`/`created_at` at a higher
   revision. `apply_snapshot` is the reconnect/replay merge: highest revision
   wins, stale frames cannot regress a row, rows are never deleted, and two
   different bodies at the same revision raise instead of flipping a coin
   (Y2.1).
2. **Hashes commit to content, never to time.** Row ids derive from
   `(session_id, generation, seq)`; row `content_hash` and every other hash are
   SHA-256 of canonical JSON (sorted keys, compact separators, UTF-8, no NaN).
   Replaying a snapshot therefore reproduces every hash independently of when
   it runs (Y2.1).
3. **Generation changes never renumber rows.** `reset_generation()` increments
   the conversation generation; existing rows stay append-only and clients
   clear their view on a generation change. This avoids seq collisions during
   reconnect (Y2.1).
4. **Model history is a real projection, not a filtered view at call time.**
   `split_history` builds immutable `ModelItem`s from model-visible rows and
   separately builds annotated `UiRow`s. `reconcile` checks exact source seq,
   content hash and byte-identical reasoning; UI redactions only change the
   UI row's `display_content`. Reasoning blobs travel unchanged, including
   whitespace and unicode (Y2.2).
5. **Screenshots are descriptors of real files.** `describe_screenshot`
   hashes bytes read from an existing local path; the descriptor's `id` commits
   to `(local_path, sha256, byte_size)`. URLs, data URIs and UNC paths are
   rejected; `assert_real_screenshot` re-reads the file. `ScreenshotRing`
   retains only the last N descriptors (default 3, configurable, 0 allowed),
   tracks `evicted_count` without accumulating unbounded audit data, and turns
   older image parts into an explicit `omitted_images` marker — never a
   placeholder image or fabricated bytes (Y2.3).
6. **Repairs are honest.** An orphan tool call gets a typed tool-result row with
   `synthetic=True`, `honest_marker="interrupted"`, `status="unknown"` and
   `"no result was recorded"`. It is model-visible so the model learns the call
   produced nothing, but it never claims success, an exit code or output. The
   repair is idempotent (Y2.4).
7. **The VNC relay is a seam, not a network client.** Credentials live only in
   the server-side `VncRelay`. `descriptor()` exposes an opaque id, a local
   endpoint path, mode and fingerprint; `assert_credential_free` fails if any
   host/username/password value or field name appears. In watch mode
   `receive_input()` drops keyboard, pointer and clipboard events *before* the
   seam forwards them; only takeover forwards them. There are no sockets, no
   noVNC dependency and no browser code in this module (Y2.14).
8. **Exposure is private-by-default and fail-closed.** `ExposurePolicy()`
   binds loopback, disables dev login, sign-ups and both share flags. A public
   bind requires auth plus a non-empty allowlist; sharing on a public bind is
   refused until both exist. `share_transcripts`/`share_screenshots` return a
   new policy (never mutate), and `can_expose` raises unless the matching
   artifact was explicitly opted in. Allowlist entries are strict emails or
   `@domain`, normalised and deduplicated; `env_reference()` documents the
   `.env`-style defaults (Y2.20).
9. **Approval and queueing are deterministic.** No uuid/rng: turn tickets,
   pending turns and relay ids derive from monotonic counters or content
   hashes. A new user message expires an awaiting-approval turn; "Always allow"
   persists per tool name; "Don't allow" executes nothing and injects a
   no-retry instruction. Explicit `readOnly` manifest flags win, slug rules
   are accepted only with a warning, and meta tools/batches always require
   approval (Y2.5–Y2.8).

## Test results

Command (from worktree root):

```
python -c "import sys,pytest; sys.path.insert(0,'keel/src'); raise SystemExit(pytest.main(['-q','keel/tests/test_transcript_contracts.py']))"
```

Result: `39 passed` (3 consecutive runs: 0.80 s / 0.89 s / 0.80 s).
Python 3.11.9, pytest 9.0.2. No existing test file was modified.

## Exact integration seams needed by the lead

This module is deliberately not wired into the live runtime. To adopt it, the
lead should make these changes (none are required for the tests above to pass):

1. **SSE protocol / `keel/events.py` (Y2.1)** — emit row-shaped events via
   `TranscriptStore.append`; send `snapshot()` on reconnect and `run` frames as
   row upserts (same `id`/`seq`, higher `updated_seq`); clients call
   `apply_snapshot` on replay. Add `seq`, `updated_seq`, `generation` and
   `provenance` to the `events` schema, and use `generation` to clear the UI
   conversation.
2. **`keel/transcript.py` (Y2.1)** — keep `TranscriptWriter` as the byte-level
   JSONL sink but write `TranscriptRow.to_dict()` lines; on restart restore via
   `TranscriptStore.restore` rather than rebuilding rows from raw dicts.
3. **Session loop / context manager (Y2.2, Y2.3, Y2.4)** — write model inputs
   through `split_history(...).model_items` into a real `model_items` table,
   keeping `llm_items` as annotated UI rows; prune image parts with
   `ScreenshotRing(prune)` before each model call; call
   `repair_orphaned_tool_calls(store)` immediately before resuming an
   interrupted turn. Redaction must rewrite only UI rows.
4. **Browser/screenshot pipeline (Y2.3)** — call `describe_screenshot` on the
   local capture path and keep descriptors, never inline bytes or remote URLs;
   configure N by passing `ScreenshotRing(capacity=N)` from settings.
5. **Queue / approvals / permissions (Y2.5–Y2.8)** — wrap each agent driver's
   turn intake in `SerialTurnQueue`; on a new user message call
   `user_message()` and treat returned ids as expired approvals. Persist
   `PendingTurn` objects with `PendingTurnFileStore` whenever approval is
   needed and `resume()` on daemon restart. Render `ApprovalCard` buttons via
   `resolve_approval`, honour `NoRetry` by injecting the instruction, and use
   `classify_connector_tool` with connector manifests (wire the `warn` sink to
   a visible warning for slug-only classifications).
6. **Desktop / noVNC bridge (Y2.14)** — keep `VncCredentials` in the daemon
   process; hand the browser only `VncRelay.descriptor().to_dict()`; route every
   inbound input event through `VncRelay.receive_input()` before it reaches the
   real VNC client. Replace `RelaySeam` with the noVNC relay implementation;
   watch mode must keep server-side filtering even if the UI is bypassed.
7. **`keel serve` / web app (Y2.20)** — apply `env_reference()` defaults,
   validate with `validate_exposure()` before binding, refuse sign-ups via
   `authorize_signup()`, ignore dev login via `effective_dev_login()`, and gate
   transcript/screenshot download or sharing endpoints with `can_expose()`.
   Pairing for public binds remains `keel/pairing.py` (C1.12).

No change to `keel/session_contracts.py` is required: that module governs the
event/journal model; this one governs transcript rows, history projection,
screenshot retention, tool repair, approvals and exposure policy.
