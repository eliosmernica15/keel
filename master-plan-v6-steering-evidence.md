# Master Plan v6 — Steering & Interrupt Evidence (X1.13, P0)

- Branch: `agent/a3-interrupt`
- Baseline: `52b752c` (`Record DeepSeek contradicted/unverifiable claims as registry known limitations`)
- Worktree: `C:\Users\Admin\.local\share\opencode\worktree\addenda\interrupt`
- Files owned (only these were changed):
  - `keel/src/keel/steering.py` (new)
  - `keel/tests/test_steering.py` (new)
  - `master-plan-v6-steering-evidence.md` (new, this document)

Requirement (plan line 1757): *"Send a message mid-turn: queue, steer at next
tool boundary, or abort-and-resume with partial output preserved."*

## Implementation

Stdlib only — `threading` (`RLock`, `Event`), `collections.deque`,
`dataclasses` (`dataclass`, `replace`), `enum.Enum`. No I/O, no network, no
third-party imports, no editable-install ambiguity.

| Symbol | Role |
| --- | --- |
| `SteeringMode` | `QUEUE` / `STEER_AT_BOUNDARY` / `ABORT_RESUME`; also aliased as `SteeringController.Mode` and `SteeringController.QUEUE` etc. |
| `SteeringMessage` | Frozen value object: `text`, `mode`, `seq`. `seq` is a monotonic total order assigned under the lock. |
| `SteeringSnapshot` | Frozen full state capture; `partial_output` is immutable `bytes`. |
| `ResumeResult` | Frozen `partial_output` bytes + ordered `messages` to inject. |
| `SteeringError` | `ValueError` subclass for invalid mode/payload. |
| `SteeringController` | Thread-safe coordinator (one `RLock` guards all state). |

Controller API:

- `submit_message(text, mode=None)` — defaults to the current mode; accepts
  enum members or strings (`"queue"`, `"STEER_AT_BOUNDARY"`, …). Every message
  is recorded in `all_messages()`; `QUEUE` → `drain_queue()`, `STEER_AT_BOUNDARY`
  → `poll_boundary()`, `ABORT_RESUME` → abort + `resume()` payload.
- `poll_boundary()` — pops exactly one boundary message in `seq` order, or
  `None`. Returns `None` after cancellation, so a cancelled turn cannot be
  steered; pending boundary messages are carried into the resume payload.
- `set_mode()` / `mode` — switch the default routing mode.
- `append_output(bytes | str)` / `partial_output` — an in-memory byte buffer;
  `str` is UTF-8 encoded, binary and invalid-UTF-8 fragments stay intact.
- `abort()` — idempotent; sets `cancel_event`, increments `abort_count` only on
  the first call, preserves the byte-exact partial output in a snapshot.
- `snapshot()` / `restore(snapshot)` — full state round-trip including
  cancellation and all message buckets.
- `resume()` — restores the abort-time output byte-for-byte via `restore()`,
  clears cancellation, returns the ordered resume messages. It overlays live
  message queues onto the snapshot so a message submitted after the abort is
  never lost; a second resume is a no-op.
- `cancel_event`, `cancelled`, `abort_count`, `drain_queue()`,
  `pending_resume_messages()`, `delivered_messages()`, `all_messages()`,
  `reset()`.

## Design decisions worth noting

1. **Deterministic order under concurrency.** `seq` is assigned while holding
   the controller lock. Boundary, queue and resume delivery are always sorted
   by `seq`. An abort message that triggers cancellation mid-queue is sorted
   back into submission order when pending boundary messages are moved to the
   resume payload (this was a real defect caught by the tests and fixed).
2. **No lost messages.** Every submit lands in exactly one of four buckets:
   queued, boundary, delivered, or resume-pending. Abort migrates (never
   deletes) boundary messages; post-abort steer messages go to resume-pending.
3. **Byte-for-byte partial output.** The snapshot copies `bytes(self._output)`;
   output appended after abort is deliberately discarded on resume, restoring
   the exact bytes captured at the abort boundary (tested with embedded NUL and
   invalid UTF-8 bytes).
4. **Idempotency.** Double abort returns an equal snapshot and does not
   re-capture output; repeated `resume()` never re-delivers messages.

## Tests (20, all passing)

`keel/tests/test_steering.py` — written before the implementation (initial run
failed with `ModuleNotFoundError: No module named 'keel.steering'`). Coverage:

1. enum members + class aliases
2. no-message boundary returns `None`
3. QUEUE messages are not delivered mid-turn
4. boundary delivery in submission order
5. boundary drains one message at a time
6. explicit mode overrides current mode
7. mode transitions (QUEUE → boundary → QUEUE → ABORT_RESUME)
8. string modes accepted / invalid modes rejected
9. messages are frozen value objects
10. 12 concurrent submitters × 50 messages: order + no loss
11. 8 concurrent submitters + 4 concurrent consumers: no duplicates, no loss
12. abort sets cancellation and preserves partial output
13. ABORT_RESUME preserves bytes byte-for-byte, including invalid UTF-8
14. double abort is idempotent
15. resume restores the snapshot after late in-flight output
16. `snapshot()` / `restore()` full round-trip
17. `restore()` round-trips cancellation state
18. cancellation propagates to boundary and preserves steered messages
19. 8 concurrent output appenders: no lost bytes
20. mixed modes (270 concurrent submits): every message in exactly one bucket

Exact verification command (from the task) and result:

```
python -c "import sys,pytest; sys.path.insert(0,'keel/src'); raise SystemExit(pytest.main(['-q','keel/tests/test_steering.py']))"
....................                                                     [100%]
20 passed in 0.70s
```

Stress: the same command was run 8 additional times consecutively; all 8 runs
reported `20 passed` (0.69–0.78 s), so the concurrent tests are not flaky.
Import path was confirmed as the worktree copy:
`.../worktree/addenda/interrupt/keel/src/keel/steering.py`.

## Integration needs (not done here — other files are not owned by this agent)

The controller is deliberately inert; the session must wire it in:

- Call `append_output(chunk)` for every chunk written to the live turn stream.
- Call `poll_boundary()` immediately before/after each tool call; treat a
  non-`None` result as an injected user message for the next model step.
- Check `cancel_event.is_set()` (or `cancelled`) in the tool loop to stop work;
  after `abort()`, use `resume().partial_output` if the session reset its
  output buffer, and feed `resume().messages` into the resumed turn.
- On a normal turn end, call `drain_queue()` to deliver queued messages into
  the next turn.
- Transport/UI layer must map its three user actions (queue / steer / interrupt)
  to the three `SteeringMode` values; identity/authorization of the sender is
  out of scope (see E3.9, owned elsewhere).

No existing source file or existing test was modified. Nothing was pushed.
