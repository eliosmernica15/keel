# Final independent security + integration review — backend completion branch

**Reviewed branch:** `integration/backend-completion-2026-11-24` (baseline `a64cd5d`)
**Snapshot reviewed:** `4c9238f`; **revalidated at current tip `45babee`** — the branch
moved during this review (see "Branch movement" below).
**Reviewer branch:** `agent/final-review1` (read-only; no tracked source modified)
**Date:** 2026-11-24
**Scope:** `backend_workflows.py`, `webapp.py`/`cli/main.py` additions, `backend_events.py`,
`backend_observability.py`, `backend_hub.py`, `backend_contracts.py`, W7 `cap_recording`
and Y4 `verify_clean_removal` fixes.

### Branch movement (important)

While this review was running, other agents merged the review report into the delivery
branch and landed follow-up commits (`0a79083`, `8f12694`, `c177c54`, `9a513f6`,
`4f32b11`, `45babee`). None of the scoped source files (`backend_workflows.py`,
`backend_events.py`, `webapp.py`, `cli/main.py`, `backend_observability.py`,
`backend_hub.py`, `backend_contracts.py`) changed between the reviewed snapshot and
`45babee`; H1–H5, M1–M5 and L1–L5 therefore still apply at the current tip. M6 has been
fixed upstream and is marked resolved below.

## Verdict

**FAIL / not releasable as-is.** The new code is substantial and most of it calls real
backend modules, and all 128 new tests pass, but four HIGH-severity defects were
reproduced: the approval workflow's possession and expiry gates are bypassable, the
idempotency/consumption guards are process-local only, and the durable event bus can be
permanently corrupted by ordinary cross-process concurrency. Several MEDIUM defects
(caller-controlled file read/write with caller-controlled permissions, wrong HTTP error
statuses, unredacted secret persistence, a permanently wedged log after an interrupted
append, and a canned MCP "invocation" reported as success) compound the risk. One MEDIUM
finding (an uncollected regression test) was fixed upstream during the review and is
marked resolved.

Good news first: the webapp endpoint correctly inherits the existing token + Origin
gate, requires a strict boolean `confirm`, and rejects unknown workflow names; the CLI
requires `--confirm`; observability redaction and its cross-process lock work under a
12-process probe; the Y4 operator-precedence fix and the W7 negative-bounds fix are
correct in the implementation; hub envelope coercion is annotation-directed and cannot
be steered to arbitrary classes by caller-supplied `type` strings.

## Findings — HIGH (fix before release)

### H1. Approval token possession is not enforced — sealed token is read back from the shared ledger
**File:** `keel/src/keel/backend_workflows.py:609` (fallback), `:581-585` (token persisted),
`:593-640` (`_approval_resolve`); exposed by `webapp.py:643` and `cli/main.py:337`.

`_approval_resolve` uses `params["token"]` only if supplied; otherwise it silently uses
the sealed token stored in `approval-events.jsonl`. Any caller that knows a `request_id`
(and a `state_root`, which the webapp endpoint accepts from the request body) can consume
an approval without ever possessing the token. The request workflow can read that ledger
(see M1), so an attacker can enumerate `request_id`s from the same file.

**Reproduction** (`probe/probe_token_fallback.py`):

```python
req = bw.run_approval_workflow({... "action": "request", ...})
rid = req["result"]["request_id"]                 # token withheld from caller
res = bw.run_approval_workflow({... "action": "resolve", "request_id": rid, ...})
```

**Evidence:** `resolve without token: True ok {'granted': True,
'reason': 'just_in_time_granted', 'remaining_seconds': 300}`.

**Fix:** require the caller-supplied sealed token for `action=resolve`; never fall back to
the stored copy. Keep the stored token only as audit evidence. Bind consumption to a
server-held secret or to the authenticated session, not to a request ID alone.

### H2. Approval TTL/expiry is controlled by the caller (`now` parameter)
**File:** `keel/src/keel/backend_workflows.py:608-629` (unseal, issuer verify, grant issue,
grant consume all use `params["now"]`); `webapp.py:643` passes params through unchanged.

A token that expired long ago is accepted when the caller claims an in-window time.
`seal_value`/`CapabilityTokenIssuer.verify`/`consume_grant` faithfully enforce the time
they are given; the workflow supplies attacker-chosen time. `ttl_seconds` is likewise
unbounded (`:570`), so a caller can mint a decades-long approval in the first place.

**Reproduction** (`probe/probe_approval.py`): request with `now=1_700_000_000,
ttl_seconds=60`; resolve with `now=1_900_000_000` fails, then resolve with
`now=1_700_000_030` and a fresh `idempotency_key` succeeds.

**Evidence:** `caller-claimed ok: True code: ok granted: True`; ledger shows
`token_dict={'expires_at': 1700000060, ...}`.

**Fix:** use only a trusted server clock (`time.time()`) for all verification and
consumption; expose an injectable clock solely through an internal/test seam, never
through the public params object. Cap `ttl_seconds` to a documented maximum.

### H3. Replay/idempotency and single-use consumption guards are process-local
**Files:** `backend_workflows.py:83-94` (`_PATH_LOCKS` in-process), `:181-209`
(`_execution` check-then-execute-persist), `:604-605` and `:632-635` (consume event check),
`:147-160` (`_append_jsonl`); `webapp.py:629-653` (threaded server, one process) vs CLI
(another process).

All locks are `threading.RLock` keyed by path. A CLI process and the webapp process (or
two webapp instances sharing `KEEL_STATE_DIR`) can pass the replay check simultaneously.
Different `idempotency_key` values are accepted by design, so an attacker can also force
fresh keys while reusing the same approval.

**Reproduction A** (`probe/probe_race.py`): 8 processes call `action=resolve` with distinct
keys for one request.

**Evidence A:** two processes got `granted=True`; the ledger contains 2 `consume` events
and 9 workflow records (including the seed) — the single-use grant was consumed twice.

**Reproduction B** (`probe/probe_race2.py`): 6 processes call `run_request_workflow` with
**identical params**.

**Evidence B:** all 6 returned `ok=True`; 6 records with the same idempotency key were
appended (`sequences: [1,2,3,4,5,6]`), i.e. no replay denial.

**Fix:** guard check-and-commit with an OS-level file lock (the pattern already used in
`backend_observability._acquire_lock`) or create an atomic `O_EXCL` consume marker/LEDGER
claim before execution. Put the approval consume marker and the replay key under the same
cross-process critical section.

### H4. `backend_events` append is not cross-process atomic; concurrent publish corrupts the durable log
**File:** `keel/src/keel/backend_events.py:637-657` (`_path_lock` is in-process only),
`:779-791` (`_JsonlStore.append` = reload → append line → replace head), `:732-777`
(strict seq/head verification).

The module advertises "atomic appends guarded by a path-keyed lock", but the lock is only
an `RLock` in one interpreter. Two processes compute the same `seq`/`prev`, both append,
and the next reader sees duplicate sequences or a broken chain. Readers can also observe
a log with no committed head while another process is mid-append.

**Reproduction** (`probe/probe_events_race.py`): 8 processes publish distinct
`SessionStarted` events to the same `state_root`, 3 trials.

**Evidence:** trial 0 wrote sequences `[1,2,2]`; reopening raised
`CorruptRecordError ... bad sequence: 2`. Trial 1 had readers fail with
`missing commit head`; trial 2 wrote `[1,2,3,4,4]`. Events were lost and the log became
unusable.

**Fix:** acquire an on-disk exclusive lock around `_JsonlStore.append` (reuse
`backend_observability`'s lock-file pattern, with safe stale-lock handling), or use an
OS advisory lock. Readers must take the same lock. Add a cross-process regression test.

## Findings — MEDIUM

### M1. Caller-chosen `project_root`/`folder` plus caller-chosen permission rules = arbitrary file read and write
**Files:** `backend_workflows.py:338-345` (`project_root` from params), `:393-410`
(`file_path` confined only to that caller-chosen root; deny/ask/allow rules and mode all
from params), `:436-469` (content returned), `:1000-1005` (`folder` + `content` written),
`webapp.py:629-643` (endpoint accepts `params` verbatim).

`_confined_file` correctly blocks `../` escapes from the chosen root, but the root itself
is attacker-chosen. With no rules supplied, `evaluate_permission(..., mode="default")`
returns `accept` for `read_file`. The recovery workflow writes `recovery-note.md` into any
caller-named directory before any verification (and still writes it when the workflow
later fails).

**Reproduction** (`probe/probe_paths.py`): create `secret_dir/credentials.txt`; call the
webapp endpoint with `project_root=secret_dir`, `file_path=credentials.txt`,
`confirm=true`. Call recovery with `folder=<other dir>`, `content="PERSISTED-BY-WORKFLOW"`.

**Evidence:** `WEBAPP status: 200 ... content: 'API_KEY=supersecret123\r\n'`; decision
`accept`; `marker written: PERSISTED-BY-WORKFLOW` even though the recovery workflow
returned `ok=False` (no search hits).

**Fix:** derive allowed roots from server configuration (`KEEL_STATE_DIR`/workdir),
not from request params; ignore caller-supplied permission rules unless an explicit
administrative opt-in exists; validate all inputs before creating/writing files.

### M2. Workflow results (including file contents) are persisted without redaction
**Files:** `backend_workflows.py:436-448`, `:450-469`, `:200-208` (`_append_jsonl` stores
the whole result), `:583-585` (unsealed `token_dict` also stored).

`observability.record_event` redacts via `keel.redaction` before persisting; the workflow
ledgers do not. A `read_file` result containing an API key is written verbatim into
`<state_root>/backend-workflows/request-results.jsonl` and into the session journal.

**Evidence:** `content in ledger: True` in `probe_paths.py` (the string
`supersecret123` appears in the JSONL). Ledger files are created with default permissions,
unlike the approval seal key which uses `0o600`.

**Fix:** apply `redact_text` to strings before writing ledger records, restrict ledger
directory/file permissions, and document ledgers as sensitive artifacts.

### M3. Wrong HTTP status mapping on the new endpoint
**File:** `webapp.py:644-651`.

The inline allowlist maps many client-side failures to 500 and maps policy denials to 400
instead of 403. `api_contracts.http_status_for_code` already exists and is used by the
capability route, but this route duplicates a partial, inconsistent table.

**Reproduction** (`probe/probe_status.py`): POST with `confirm=true` and
`operation="network_egress"` / `headers` mismatch / `manifest=123`.

**Evidence:** `operation_denied → 500`, `csrf_denied → 500`, `bad_manifest → 500`;
`path_escape → 400`, `bound_exceeded → 400`. Policy denials should be 403; malformed
input 400; unknown/internal 500 per the canonical contract.

**Fix:** call `api_contracts.http_status_for_code(code, default=...)`, extend
`ERROR_STATUS` with workflow codes (`operation_denied`, `csrf_denied` → 403;
`bad_manifest`, `bad_ttl`, `unknown_action` → 400), and use the canonical error envelope.

### M4. An interrupted event append permanently wedges the log
**File:** `backend_events.py:788-790` (log line fsynced, then head atomically replaced),
`:732-777` (head mismatch ⇒ `CorruptRecordError` on every read and append).

There is no recovery path for the crash window between the two writes: a single event can
remain in the JSONL while the head still declares the previous count, after which
`EventBus(...)` and `publish()` both fail forever.

**Reproduction** (`probe/probe_head_crash.py`): publish one event, then restore the head
to `{"count":0,"digest":"0"*64}` to simulate the crash.

**Evidence:** reopen raises `CorruptRecordError ... commit head mismatch`; subsequent
`publish` raises the same.

**Fix:** write a small intent/prefix record that can be completed or rolled forward on
reload, or reconstruct the head from a validated trailing prefix instead of treating any
mismatch as permanent corruption.

### M5. MCP "invocation" is canned and `server_config` is never executed
**Files:** `backend_workflows.py:56-66` (fixed inline programs), `:865-870`
(`server_config` only normalized), `:921-935` (subprocess always runs the fixed program),
`:963-977` (`ok=True` even when `failure` is set).

The workflow reports a real subprocess result, but the subprocess only hashes
`tool + "\0" + args`; the caller's configured MCP server command is ignored. A failed
invocation still returns top-level `ok=True, code="ok"` with `outcome="failure_handled"`,
so callers checking `ok` see success.

**Evidence:** `test_mcp_workflow_handles_real_failure_and_denies_all_tools` asserts
`failed["ok"] is True` while `result["failure"]["reason"] == "tool_failure"`.

**Fix:** either execute the validated, sandboxed `server_config.command` as the actual
invocation target, or rename/document the step as a deterministic simulation and set
`ok=False` (with a distinct code) when the tool call fails.

### M6. Regression test for the W7 `cap_recording` fix was never collected — RESOLVED upstream
**File (reviewed snapshot):** `keel/tests/test_w7_x1_y5_d1_backend.py:690` (nested inside
`test_y3_8_browser_bound_pairing` at `:656`, with an undeclared `self` parameter).

At `4c9238f`, `test_w7_11_cap_recording_rejects_negative_bounds` was indented as a nested
function and invisible to pytest. The W7.11 fix itself (`w7_x1_y5_d1_backend.py:740-743`)
was correct, but its claimed regression guard did not run.

**Evidence (snapshot):** `pytest --collect-only` reported 39 collected tests in that file
versus 40 `def test_...` definitions; the missing test was exactly
`test_w7_11_cap_recording_rejects_negative_bounds`.

**Resolution:** branch commit `9a513f6` dedented the test to module level and replaced
`self.assertRaises` with plain `pytest`-style `try/except`. Re-collection at current tip
`45babee` includes the test. No further action needed.


## Findings — LOW

* **L1 — `ttl_seconds=0` silently becomes 300.** `backend_workflows.py:570` uses
  `int(params.get("ttl_seconds") or 300)`, so a caller asking for zero TTL gets a
  5-minute token. Repro: `probe_status.py` "approval bad ttl" → `200 code=ok`.
  Same `or` pattern weakens `max_children=0` (`:718`) and `memory_limit=0` (`:382`).
  Use explicit `is None` checks and validate bounds.
* **L2 — Approval CSRF guard is caller-controlled.** `backend_workflows.py:553-560`
  takes both `headers` and `expected_origin` from params, so a client can supply matching
  values or omit both. The webapp's own Origin check protects the HTTP surface; the CLI
  has none. Do not present this as an independent CSRF control.
* **L3 — Approval key file creation has an empty-file race.**
  `backend_workflows.py:494-513` creates the seal key with `O_EXCL` and writes it in a
  second step; a concurrent reader can see a zero-length file, quarantine it with
  `os.replace`, and rotate the key while another process is using the old one. Write the
  key before making the path visible (temp file + atomic `os.replace`/link), under a
  cross-process lock.
* **L4 — `annotation_schema` mislabels `Literal` values.** `backend_contracts.py:566-568`
  always emits `{"type": "string"}` even for `Literal[1, 2]`. Derive the type from the
  argument values.
* **L5 — Workflow `state_root` is not confined.** `backend_workflows.py:111-116` accepts
  any caller path and creates it. Combined with H1/L2 this allows cross-session access
  when multiple principals share one webapp. Bind `state_root` to server configuration.

## Verification performed

* Ran the full new test set against the reviewed snapshot: `test_backend_workflows`,
  `test_backend_contracts`, `test_backend_contracts_hardening`, `test_backend_events`,
  `test_backend_hub_integration`, `test_backend_observability` — **128 passed**.
  These files are unchanged at current tip `45babee`.
* Ran 252 existing cap/hub/webapp/CLI tests — all passed except two pre-existing
  environmental failures that also fail on baseline `a64cd5d`:
  `test_release_integrity.py::test_integrity_cli_on_real_artifacts` (release artifacts
  absent from the git archive) and `test_webapp.py::test_run_streams_events_and_done_marker`
  (local socket timeout). Neither is caused by this branch.
* A full-suite run against the *stale* `probe/int` extraction produced
  **6 failed, 4184 passed, 51 skipped**. One of those,
  `test_permission_contracts.py::test_w39_concurrent_approval_writes_are_lossless`, was
  an order/timing-dependent Windows `PermissionError` (1 failure in 6 isolated reruns);
  it was fixed upstream by branch commit `4f32b11` (path-keyed in-process lock plus
  unique `mkstemp` temp files). The other five were missing release artifacts / changed
  downloaded plan hashes. A separate clean-checkout full-suite result recorded on the
  branch (`REVIEW-FINAL-QUALITY.md`, commit `49c551e`) likewise reports no deterministic
  regression attributable to the eight batches.
* Reproduction scripts are in `probe/*.py`. The `probe/int` and `probe/base` directories
  are stale throwaway extractions from early in the review; re-extract the desired tip
  before re-running any script.
* Confirmed redaction (`probe_observability.py`): secrets in nested dicts/lists were
  `[REDACTED]` and no plaintext appeared in the log; 12 concurrent `record_event` calls
  produced a valid 12-event chain.
* Confirmed envelope coercion safety (`probe_hub.py`): `coerce_value` is
  annotation-directed; caller `type` strings such as `os.system`/`subprocess.Popen` are
  not resolved or instantiated. `ModelId` round-trips and the discovery-id routing error
  behave as documented.

## Prioritised remediation order

1. H1 — remove the stored-token fallback; require caller possession.
2. H2 — trusted clock + bounded TTL.
3. H3 — cross-process lock/atomic claim for replay and consumption.
4. H4 — cross-process lock for the event bus append/read path.
5. M1/M2 — confine roots, ignore caller permission rules, redact persisted results.
6. M3/M4/M5 — status mapping, crash recovery, honest MCP outcome. (M6 was fixed upstream.)

---

# RE-VERIFICATION (final follow-up)

**Branch tip re-tested:** `e848c5d` (fetched from `origin`, `probe/int` re-extracted from
that commit). All original probes were re-run unchanged unless noted; adapted probes are
in `probe/reverify_adapted.py`.

## Result: PASS — every HIGH and MEDIUM finding is CLOSED

| ID | Finding | Original probe re-run at `e848c5d` | Result |
|---|---|---|---|
| H1 | Stored-token fallback / no possession check | `probe_token_fallback.py` | **CLOSED** — `resolve without token: False missing_token`. `backend_workflows.py:816-842` now requires a string token and compares its SHA-256 to `sealed_digest` with `hmac.compare_digest`; `token_dict` is no longer written to the ledger. |
| H2 | Caller-controlled clock / TTL | `probe_approval.py` plus adapted monkeypatch of `bw._now` (the original script's final resolve is now a legitimate replay denial, not an expiry bypass) | **CLOSED** — with a token issued at fake time `1_700_000_000` (TTL 60) and the real clock restored, a resolve claiming `now=1_700_000_030` returns `False invalid_token`. `_now()` at `:90-97` is module-level and params are ignored; TTL is bounded to 1…86400 (`:769-781`). |
| H3 | Process-local replay / single-use guards | `probe_race.py`, `probe_race2.py` | **CLOSED** — race probe: 1 `consume` event, 1 successful grant, 7 `replay_denied`; identical-params probe: 1 success + 5 `replay_denied`, 1 ledger record. `_locked_path()` (`:153-231`) adds `O_EXCL` cross-process locks around check-and-commit. |
| H4 | Non-atomic event log appends | `probe_events_race.py` (3 trials × 8 processes) | **CLOSED** — all 3 trials: 8 lines with sequences `[1..8]`, 8 successful publishes, `read ok (8 events)`, no `CorruptRecordError`. `_LogLock` at `backend_events.py:784-882` adds an OS-level exclusive lock; appends are single durable writes (`:892-909`). |
| M1 | Arbitrary file read/write via caller-chosen roots | `probe_paths.py` (adapted wrapper for the final assertion) | **CLOSED** — `REQUEST ok: False path_escape`, `content leaked: False`; `RECOVERY ok: False path_escape`, no marker file. Webapp POST returned `400 path_escape`. `project_root`/`folder` are confined under `state_root` (`:475-503`, `:523-532`, `:1253`); caller allow/ask rules are ignored (`:594-609`). |
| M2 | Unredacted secrets in workflow results/ledgers | `probe_paths.py` + `probe/reverify_adapted.py` | **CLOSED** — `plaintext in response: False`, `plaintext in ledger: False` for a file containing `API_KEY=supersecret123`; `_redact()` is applied before both persistence and return (`:233-247`, `:309`, `:435-438`). |
| M3 | Wrong HTTP status mapping | `probe/reverify_adapted.py` webapp POSTs | **CLOSED** — `operation_denied → 403`, `csrf_denied → 403`, `bad_manifest → 400`, `ttl_zero → 400 bad_ttl`, `path_escape → 400`. `webapp.py:643-661` consumes `result["http_status"]`; `backend_workflows._HTTP_STATUS_HINTS` supplies it. |
| M4 | Interrupted append permanently wedges event log | `probe_head_crash.py` | **CLOSED** — after rolling the `.head` back to `count=0`, `reopen: ok 1` and `append after corruption: ok`; `backend_events._read()` (`:1015-1085`) rolls the committed head forward for a verified trailing record. |
| M5 | Canned MCP invocation reported as success | `probe/reverify_adapted.py` | **CLOSED** — success path: `ok=False code=dry_run dry_run=True command_executed=False`; failure path: `ok=False code=tool_failure outcome=failure_handled`. `backend_workflows.py:1184-1217` labels the step as a dry run and no longer reports `ok=True`. |
| M6 | Uncollected W7 regression test | `pytest --collect-only` | **CLOSED** — `40 tests collected`, including `test_w7_11_cap_recording_rejects_negative_bounds`. |

**Test evidence at `e848c5d`:** 183 passed for the six backend test files plus
`test_w7_x1_y5_d1_backend.py`; 252 existing cap/hub/webapp/CLI tests passed with only the
known baseline-environmental `test_run_streams_events_and_done_marker` socket timeout.

## Remaining findings (LOW, non-blocking)

* **L2 (still open)** — the workflow's own `headers`/`expected_origin` CSRF check still
  accepts both values from params (`backend_workflows.py:751-758`). The webapp's independent
  Origin gate covers HTTP; do not treat the workflow check as an independent control.
* **L3 (still open)** — `backend_workflows._approval_key_file` (`:693-713`) still creates
  the key with `O_EXCL` and writes its bytes in a second step, leaving a theoretical
  empty-file/rotation race across processes.
* **L4 (still open)** — `backend_contracts.annotation_schema` (`:566`) still emits
  `{"type": "string"}` for non-string `Literal` values.
* **L1, L5 (resolved/accepted)** — `ttl_seconds=0` now returns `400 bad_ttl`; `state_root`
  is still caller-selectable but is now the trust anchor for all path confinement, so it
  is no longer a cross-boundary escape.

**Final verdict: PASS.** No HIGH or MEDIUM finding from the original review is
reproducible at integration HEAD `e848c5d`. Only the three LOW items above remain.
