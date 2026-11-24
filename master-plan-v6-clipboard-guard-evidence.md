# Master Plan v6 — X5 clipboard/screen guard verification evidence

- **Worktree:** `C:\Users\Admin\.local\share\opencode\worktree\addenda\a8-x5`
- **Branch:** `agent/a8-x5`
- **Baseline:** `4e0b804` ("Mark E5 verified; retain D7 intelligence contracts without false ID attribution")
- **Scope:** every `status=not_started`, `priority=P0` row in `PLAN-INDEX.json`
  whose ID begins with `X5.` — **X5.1, X5.5, X5.6** — plus the primary
  clipboard/screen-guard row named in the task brief, **X5.9** (registry
  priority `P1`). X5.9 is the module's subject and the source of the file
  names; the three P0 rows are included so the "all not_started P0 X5.x rows"
  instruction is also satisfied in full. No other X5 row was touched.
- **Files owned / changed:** three new files only —
  `keel/src/keel/clipboard_guard.py`, `keel/tests/test_clipboard_guard.py`,
  and this evidence file. **No existing file was edited.**

## 1. Plan rows implemented

| ID | Feature implemented | Where |
| --- | --- | --- |
| X5.9 | Clipboard/screen guard: explicit approval, tainted-source rules, no silent capture, deterministic descriptors, fail closed | `ClipboardScreenGuard`, `Approval`, `CaptureDescriptor`, `Decision` |
| X5.1 (P0) | Sensitive-project mode: flag hard-blocks remote providers/connectors; lock badge | `ProjectFlags`, `SensitiveProjectPolicy` |
| X5.5 (P0) | Mass-change guard: per-minute mutation rate limit; breach pauses the agent and requires a snapshot | `MutationEvent`, `MassChangeGuard`, `MassChangeDecision` |
| X5.6 (P0) | Filesystem change journal: per-task touched-path set, reviewable and revertible as a set | `JournalEntry`, `ChangeJournal` |

## 2. Approach

Everything is **stdlib-only, pure descriptors and policies**. The module never
reads a real clipboard, never captures a screen, never touches the filesystem
and never opens a socket. Callers supply content/events; the module computes a
decision and metadata. This makes the security properties testable without any
ambient OS capability.

### X5.9 gate chain

A read is allowed only when *all* of these hold:

1. A non-`None` `Approval` exists with a non-empty `approver` and `approval_id`.
2. Its `source` and `purpose` match the request exactly (scoped grant).
3. `issued_at <= now <= expires_at` (time-boxed; expired grants deny).
4. The descriptor's schema is recognised, `source` is one of the four known
   sources, and `purpose` is non-blank.
5. If the capture is tainted, an explicit `taint_acknowledgement` of
   `"acknowledged"` is present.
6. Optionally, `verify_content` recomputes the descriptor's fingerprint and
   taint from the supplied content; any mismatch adds `descriptor_tampered_or_fabricated`.

Any failure produces `allowed=False` with an explicit reason code. There is no
default/implicit grant path.

Taint is detected from three independent signals: screen-origin sources
(`screen`, `screen_region`, `screenshot`) are tainted by definition; content is
scanned for six secret patterns (PEM private-key blocks, AWS keys, OpenAI keys,
GitHub tokens, bearer tokens, generic secret assignments); and caller labels
such as `secret`/`pii` are honoured. A tainted descriptor is always flagged —
the flag survives even when an acknowledgement allows the read.

### Determinism and no fabrication

Descriptors and decisions are frozen dataclasses serialized with
`json.dumps(..., sort_keys=True, separators=(",", ":"))`. Taint reasons are
emitted in dict/label order and journal/revert plans are explicitly sorted or
reversed. Digests are computed only from actually supplied content or events;
absent content yields `content_fingerprint=None` rather than a hash of a
stand-in. `verify_descriptor` rejects a descriptor whose claimed fingerprint
or taint level does not match the content, so a forged "clean" descriptor
cannot be laundered. `evaluate` also ignores a tampered `descriptor.approved`
flag and re-derives the approval decision from the authoritative `Approval`.

### P0 rows

- **X5.1:** `remote_allowed()` returns `True` only when the project is not
  sensitive *or* the provider kind is explicitly local (`local`, `builtin`,
  `local_model`). Unknown kinds are treated as remote (fail closed). `badge()`
  returns a lock glyph only for sensitive projects.
- **X5.5:** events outside the window and non-mutating actions are ignored;
  `count > limit` yields `breached=True`, `pause_agent=True`,
  `snapshot_required=True` and a SHA-256 digest of the sorted counted events.
  Below the limit, no snapshot digest is fabricated (`None`).
- **X5.6:** entries get monotonic sequence numbers; `review()` returns a
  task's entries, `paths()` a sorted unique set, and `revert_plan()` the
  reversible entries in reverse order. There is intentionally no method that
  applies changes to disk.

## 3. Results

Command used (the installed `keel` points at the main clone, so `src` is put
first on the path):

```
cd <worktree>/keel
$env:PYTHONPATH="src"
python -m pytest -q tests/test_clipboard_guard.py
```

Result: **31 passed in 0.83s** (0 failed, 0 skipped).

### Adversarial checks (all passing)

| Attack / property | Test | Expected outcome |
| --- | --- | --- |
| Read with no approval | `test_x59_no_approval_denies` | `allowed=False`, reason `no_explicit_approval` |
| Expired / future / empty-approver / empty-id grant | `test_x59_expired_approval_denies`, `test_x59_not_yet_valid_approval_denies`, `test_x59_missing_approver_or_id_denies` | deny with the matching reason |
| Wrong source or purpose on the grant | `test_x59_scope_mismatch_denies` | deny; scope is exact |
| Secret-looking clipboard content | `test_x59_secret_content_is_flagged_and_denied`, `test_x59_private_key_block_flagged` | `tainted=True`, `classification="secret"`, deny without ack |
| Screen capture | `test_x59_screen_source_is_tainted_and_flagged`, `test_x59_acknowledged_taint_allows_but_still_flags` | always flagged; `taint_source` reason; ack required to allow |
| Tainted content laundered to "clean" descriptor | `test_x59_verify_descriptor_rejects_tampered_taint` | `verify_descriptor=False`, `descriptor_tampered_or_fabricated` deny |
| Forged fingerprint | `test_x59_verify_descriptor_rejects_forged_fingerprint` | `verify_descriptor=False`, decision denied |
| Forged `approved=True` bit | `test_x59_tampered_approved_flag_cannot_grant` | ignored; no approval still denies |
| Unknown source / blank purpose | `test_x59_unknown_source_fails_closed`, `test_x59_empty_purpose_fails_closed` | deny (fail closed) |
| Silent OS access | `test_x59_module_has_no_os_clipboard_screen_or_network_imports` | AST assert: no `pyperclip`, `pyautogui`, `PIL`, `ctypes`, `subprocess`, `socket`, `requests`, `urllib`, `win32clipboard` imports |
| Raw content leak | `test_x59_no_raw_content_leaks_into_decision_json` | content absent from serialized decision; only its fingerprint appears |
| No fabricated digest | `test_x59_absent_content_is_never_fabricated` | `content_provided=False`, length and fingerprint `None` |
| Determinism | `test_x59_descriptors_are_deterministic`, `test_x59_fingerprint_is_exact_sha256` | identical inputs -> identical canonical JSON; exact SHA-256 |
| Sensitive project egress | `test_x51_sensitive_project_blocks_all_remote_kinds`, `test_x51_sensitive_project_allows_only_explicitly_local` | remote denied, only explicitly local allowed |
| Mass change | `test_x55_within_limit_is_not_a_breach`, `test_x55_breach_pauses_and_snapshots`, `test_x55_out_of_window_and_non_counted_actions_ignored` | pause+snapshot only above limit within window |
| Change journal | `test_x56_records_reviews_and_reverts_as_a_set`, `test_x56_journal_is_deterministic_and_has_no_apply_api` | ordered review/set paths/reverse revert plan; no apply API |

## 4. Honest limitations

- This is a **policy/descriptor layer, not a live OS integration**. By design
  (and per the brief) it performs no actual clipboard read, screen capture,
  filesystem mutation or network request. Wiring it into a real capture tool
  would require editing that tool's file, which is outside this worktree's
  file ownership.
- Taint detection is a pattern heuristic. It deliberately errs toward tainting
  (screen sources are always tainted and secrets are denied without an
  acknowledgement), but it does not claim to be a complete DLP scanner.
- The module does not persist approvals, journals or snapshots; callers own
  storage and replay. This keeps the implementation deterministic and pure.
