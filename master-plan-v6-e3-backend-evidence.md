# E3 backend — implementation evidence (13 P1/P2 subagent rows)

**Branch:** `agent/b2-e3` · **Baseline:** `982335d`
**Worktree:** `C:\Users\Admin\.local\share\opencode\worktree\backend\b2-e3`

## Scope and registry note

The assignment was to implement backend behaviour for every `not_started` **E3.\***
row except the two P0 rows already handled in `keel.result_contracts.py`.
Reading `Keel_Master_Plan_v6.md` and `REMAINING-BACKEND-ANALYSIS.txt` at the
assigned baseline found exactly **13** `not_started` E3 rows (all P1, milestone
M12 except E3.15 which is M8). Their full acceptance text is reproduced here
for traceability:

| ID | Full registry feature text | Milestone | Status at baseline |
| --- | --- | --- | --- |
| E3.1 | One activation API for local children and external executions; provider capability flags (`agent_options`, `agent_preset`, `output_schema`, `depth_limit`) validate start options before anything starts. | M12 | `not_started` / P1 |
| E3.2 | Result delivery policy: parent (notifies the model) vs caller (only returns result, e.g., workflows/code mode). | M12 | `not_started` / P1 |
| E3.4 | Child working directory chosen at admission (relative resolves against the parent's current dir); local child keeps the parent's original project; resumed child retains logged directory state. | M12 | `not_started` / P1 |
| E3.5 | Local child = durable session with at most one live activation; manager owns identity/capacity reservation, input admission, cold resume, child-first disposal; structured-output capture closes input for that activation; resume does not inherit the schema. | M12 | `not_started` / P1 |
| E3.6 | Spawn vs Fork: fork seeds the child with the parent's completed-turn prefix (contiguous, lossless, balanced steps), spawn starts fresh; `inherits_parent_context` is descriptive for wording only. | M12 | `not_started` / P1 |
| E3.7 | External backends as providers (separate coding CLIs or protocol agents): one execution, no follow-ups, results to creator only while online. | M12 | `not_started` / P1 |
| E3.9 | Messaging within one tree: running target gets *steer*, absent target cold-resumes, sender identity rechecked, accepted messages never retracted. Two distinct message source kinds: `agent-message` (relay: words the sender chose) vs `subagent-settled` (runtime notice about how a child ended) so a child is never credited with words it didn't write. | M12 | `not_started` / P1 |
| E3.10 | Interrupt authority: only the user or an exact live ancestor; fire-and-return; preserves unclaimed inbox, the activation and descendants; claimed work not requeued; absent target is a no-op. | M12 | `not_started` / P1 |
| E3.11 | Whole-tree drain and wait-for-tree-work (idle members with parked input stay resident without delaying host completion). | M12 | `not_started` / P1 |
| E3.12 | Parent-owned subagent catalog projection (membership at creation, no execution status); recursive `list_descendants` with parent id, depth, path and per-branch diagnostics (`unsupported`, `corrupt`, `unavailable`); cycles/repeats skipped; unreadable branch stops only that branch; historical children with unavailable descriptors listed as `unknown` mode with no continuation rights. | M12 | `not_started` / P1 |
| E3.13 | Subagent model-route setting: default-off allowlist of provider/model routes the agent may choose for children; reads live on each delegation; malformed/duplicate routes error. | M12 | `not_started` / P1 |
| E3.14 | User-authored message to a child from the UI with attachments (image parts admitted via attachment store; model must accept images) and client time zone; cold resume at capacity rejects with a typed `delivery-unavailable`. | M12 | `not_started` / P1 |
| E3.15 | Lifecycle events `subagent/start`, `subagent/end` (scoped to tree root), provider added/removed. | M8 | `not_started` / P1 |

**P0 verification/documentation:** `E3.3` (agent names) and `E3.8` (results,
sanitized diagnostics, stop reasons) were already implemented in
`keel/src/keel/result_contracts.py` and `keel/tests/test_result_contracts.py`.
This change did **not** edit either file.  Instead `e3_backend.py` imports and
reuses `validate_agent_name`, `make_agent_name`, `Result`, `StopReason`,
`build_result`, `child_failure_to_result` and `parse_stop_reason`, retypes the
result-contract validation error at its host boundary, and exposes the
executable check `verify_p0_contracts() -> {"E3.3": True, "E3.8": True}`.
Tests `TestP0Verification` and a combined pytest run prove those P0 surfaces
are still live.

`PLAN-INDEX.json`, `parity.json`, `Keel_Master_Plan_v6.md`, the registry status
and all other existing files were **not** edited.  No row status was changed
here; this evidence does not claim the full M12 fleet UI or a real provider
runtime was shipped.  The deliverable is the host-side, stdlib-only backend
behaviour those features require.

## Files owned (only these were added)

* NEW `keel/src/keel/e3_backend.py` (1,396 lines)
* NEW `keel/tests/test_e3_backend.py` (60 tests, 724 lines)
* NEW `master-plan-v6-e3-backend-evidence.md` (this file)

## Required behaviour → implementation map

| Requirement | Surface in `keel.e3_backend` |
| --- | --- |
| E3.1 one activation API + four flags | `ActivationRequest` + `SubagentManager.start`; `Capability`, `ProviderCapabilities`, `StartOptions`, `validate_start_options`. Capability errors are raised **before** node creation, capacity reservation, activation creation or event emission (test asserts zero mutation). |
| E3.2 delivery policy | `DeliveryPolicy.PARENT/CALLER`, `Settlement`, `DeliveryOutcome`; `settle()` emits an unattributed `subagent-settled` notice to the parent on `parent`, and returns the result to the caller only on `caller`. |
| E3.4 cwd at admission | `ChildWorkingDirectory`, `resolve_child_cwd` (lexical POSIX/Windows-drive absolute detection, relative joined against parent's resolved cwd, project inherited from parent); cold resume reuses the logged `ChildNode.cwd`. |
| E3.5 durable child / one live activation | `ChildNode` (identity, membership, logged cwd, no status) and `Activation` (one execution). Manager owns `capacity`, `_live_count`, `_cold_resume`, `AlreadyActive`, `DeliveryUnavailable`, `dispose_tree` (child-first). A schema-bearing activation sets `input_closed=True` on settle; resume builds `StartOptions()` with no schema. |
| E3.6 spawn vs fork | `SpawnMode`, `TurnStep`, `ForkSeed`, `compute_fork_prefix` (contiguous complete steps only, no loss, balanced open/close groups), `ForkPrefixError`; `inherits_parent_context` is stored only in `inherits_parent_context_is_wording` and is excluded from behavioural state (test compares two states). |
| E3.7 external backends | `Capability.EXTERNAL_EXECUTION`, `ProviderRecord.online/removed`, `Activation.one_shot`; `_cold_resume` raises `NoFollowUp` for a settled external execution; `settle()` withholds a result from an offline creator (`reason="creator-offline"`). |
| E3.9 messaging | `send_message` rechecks sender identity, steers a live target (`claimed=True`, recorded in `Activation.steered`) and cold-resumes an absent one (parked, unclaimed). `MessageSource.AGENT_MESSAGE` relays caller text with `attributed_to_child=True`; `_settled_notice` emits `SUBAGENT_SETTLED` with `attributed_to_child=False` and runtime wording, never the child's final text. No API retracts an accepted message. |
| E3.10 interrupt | `interrupt` accepts only `USER_ACTOR` or an exact live ancestor (parent chain + live check), else `InterruptDeniedError`. Returns `InterruptReceipt` immediately with `INTERRUPT_REQUESTED` status; preserves steered + parked inbox, the activation and descendants; leaves claims untouched; an absent target returns a no-op receipt. |
| E3.11 drain / wait | `drain_tree` settles live work in child-first order and returns `DrainReport`; `wait_for_tree_work` returns `TreeWorkStatus(host_can_complete=not live)` so parked input never blocks host completion. Resident nodes are not removed by a drain. |
| E3.12 catalog projection | `CatalogEntry`, `list_descendants` walks parent-owned `child_ids` with a `visited` set (cycles/repeats skipped), emits parent id/depth/path, and emits `UNSUPPORTED`/`CORRUPT`/`UNAVAILABLE` diagnostics that stop only that branch; unavailable providers/descriptors become `AgentMode.UNKNOWN` with `continuation_rights=False`. No execution-status field exists on the entry. |
| E3.13 route allowlist | `ModelRoute`, `parse_model_route`, `ModelRouteAllowlist`, `set_route_allowlist`; default `enabled=False`, `check_route` reads `manager.route_allowlist` on every `start` (live reconfiguration test), malformed routes and duplicates raise `RouteError`, disallowed routes raise `RouteNotAllowed`. |
| E3.14 UI message + attachments | `Attachment` (opaque `store_ref`, never a payload), `send_message(attachments=..., client_timezone=...)`; only `image/*` parts require `Capability.IMAGES` **and** `accepts_images`, else typed `ImageNotAccepted`; cold resume at capacity raises `DeliveryUnavailable` with code `DELIVERY_UNAVAILABLE`. |
| E3.15 lifecycle events | `LifecycleKind`/`LifecycleEvent`; `subagent/start` emitted in `_new_activation`, `subagent/end` in `settle`, both scoped via `_tree_root_of`; provider added/removed emitted with `tree_root=None` and excluded from `events_for_root`. |
| Fail-closed / purity | Coded `E3Error` subclasses for every rejection; boundary validators reject malformed ids, text, enums and mappings; P0 `ContractValidationError` retyped as `E3ValidationError`; module imports only `__future__`, `posixpath`, `re`, `dataclasses`, `enum`, `typing` and the sibling `result_contracts` (AST test forbids os/sys/subprocess/socket/time/random/etc.); no file, network, subprocess, clock or chance input. |

## Verification

Both commands were run from the worktree root.

```
python -c "import sys,unittest; sys.path.insert(0,'keel/src'); \
suite=unittest.defaultTestLoader.discover('keel/tests',pattern='test_e3_backend.py'); \
raise SystemExit(0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1)"
```

Result: **60 tests passed in 0.094 s** (stdlib-only runner).

```
python -c "import sys; sys.path.insert(0,'keel/src'); import pytest; \
raise SystemExit(pytest.main(['-q','keel/tests/test_e3_backend.py', \
'keel/tests/test_result_contracts.py']))"
```

Result: **120 passed, 76 subtests passed in 5.87 s** — the 60 new E3 backend
tests plus the 60 existing P0 result-contract tests, no failures or warnings.

`python -m py_compile keel/src/keel/e3_backend.py keel/tests/test_e3_backend.py`
also succeeded.  (`ruff` is not installed in this environment, so no lint run
is claimed.)

## Adversarial coverage (all green)

* **Start validation** — each of the four E3.1 flags is removed in turn and the
  matching option is rejected with `CAPABILITY_NOT_SUPPORTED`; no node,
  activation or tree-scoped event is created in any of the four cases.
* **Capacity and lifecycle** — a live child cannot get a second activation;
  `capacity=1` produces a typed `DELIVERY_UNAVAILABLE` on cold resume; a
  structured settle closes input and rejects steering with `INPUT_CLOSED`, and
  the resumed activation provably has no schema.
* **Fork prefix** — incomplete-before-complete, unclosed groups, mismatched
  closes and a missing seed are all rejected; the wording-only inheritance flag
  changes no behavioural field.
* **External one-shot** — no follow-up after settle (`NO_FOLLOW_UP`), and an
  unregistered provider withholds the result from the creator while still
  returning the sanitized result to the caller.
* **Message attribution** — the parent notice is `subagent-settled`,
  `attributed_to_child=False` and does not contain the child's final-output
  text; accepted messages survive settle and drain; duplicate message ids are
  rejected.
* **Interrupt** — a sibling or a settled ancestor is denied with
  `INTERRUPT_DENIED`; a missing target is a silent no-op; a fire-and-return
  interrupt preserves steered and parked items, the activation, descendants
  and the claim state.
* **Catalog diagnostics** — corrupt/unavailable descriptors and a provider that
  no longer advertises external execution produce per-branch diagnostics with
  no continuation rights; a corrupt branch does not hide its healthy sibling;
  cycles and repeated membership entries are skipped.
* **Routes and attachments** — default-off, live disable/re-enable, malformed
  (`nope`, `/model`, `provider/`, traversal) and duplicate routes all fail
  closed; image parts are admitted only for image-capable providers, while a
  text attachment needs no image capability.
* **Credentials and purity** — secret-bearing structured output is refused at
  the host boundary with a coded `E3ValidationError`, diagnostics are sanitized
  through the reused E3.8 surface, and the AST import audit confirms no host
  resources are touched.
