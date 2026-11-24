# Master Plan v6 — Fleet Event-Bus Repair Evidence (Agent 24)

Worktree: `C:\Users\Admin\.local\share\opencode\worktree\final\fleet-events`
Branch: `agent/f-fleet-events` · Baseline: `463481edb0f325e9250d9dd5bf559ff5f138a55d`

All commands below were run from the worktree root with
`$env:PYTHONPATH = 'keel/src'` (PowerShell).

---

## 1. Defect (confirmed by the product-defect agent, §4.1)

The Fleet event bus was **disconnected and non-persistent**:

* `keel/src/keel/capability_registry.py::_bus` (baseline lines 1451–1457)
  constructed a brand-new `EventBus()` on *every* invoke.
* Baseline `keel/src/keel/automation.py::EventBus` had
  `def __init__(self):` and `history: list[dict] = []` — an in-process list with
  no state-root parameter and no disk write.
* Three publishes therefore each returned a **1-item** history; **zero** state
  files were written; a fresh bus (or process) saw no earlier events.
* `fleet.anomaly` (`_anomaly`, baseline lines 1444–1448) called
  `workflow_history.anomaly_score(p.get("events", []))` — it scored only events
  supplied by the caller and never read anything the bus had published.

Referred reproduction output (product-defect evidence §4.1):

```
publish #1: history=[{'topic': 'task.done', 'payload': {'id': 't1'}, ...}]
publish #2: history=[{'topic': 'task.done', 'payload': {'id': 't2'}, ...}]
publish #3: history=[{'topic': 'task.done', 'payload': {'id': 't3'}, ...}]
state files: []
```

### Independent baseline probe (this agent)

Baseline `automation.py` was extracted with
`git show 463481e:keel/src/keel/automation.py` and loaded in isolation; three
separate `EventBus()` objects were published to:

```
histories: [1, 1, 1]
accepts state_root: False -> EventBus.__init__() takes 1 positional argument but 2 were given
jsonl files: []
```

---

## 2. Fix implemented (owned files only)

### `keel/src/keel/automation.py`

1. `EventBus(state_root=None, *, filename="eventbus.jsonl")`:
   * `self.path = Path(state_root) / filename` when a state root is supplied,
     otherwise `None`.
   * On construction, `_load()` reloads all history from the JSONL file
     (missing file → `[]`; malformed lines are skipped, never fatal).
   * `publish()` appends the event to `history`, then `_append()` writes one
     JSON line to `<state_root>/eventbus.jsonl` (creating parent dirs), then
     dispatches to subscribers exactly as before. Publish's return value
     (subscriber count) and the event shape are unchanged.
   * With no `state_root`, behaviour is byte-for-byte the old in-memory
     behaviour (`path is None`, no disk access), so `test_automation.py` and
     existing E2E single-publish assertions still pass.
2. Event-aware anomaly logic, also in `automation.py`:
   * `anomaly_score(events=None, *, state_root=None, window=10)` and
     `EventBus.anomaly_score()` consume the **real** event history: repeated
     `denied`/`error` kinds (also `.denied`/`.error` topics and a truthy
     `payload["denied"]`), destructive tools (`delete_file`, `process_kill`),
     and mass file reads (`read_file` / `file_read` / `kind=file_read` above
     20 over the whole history → score floor 0.8). Bus events are normalized
     via `_fields()` so both `{"topic":..., "payload":{...}}` and raw payload
     dicts are scored.
   * If no events are supplied but `state_root` is given, the persisted
     `EventBus(state_root).history` is loaded and scored — this is the
     connected "workflow run → event bus → anomaly detection" path.
   * Only when there are **no events at all** (no explicit list and no state
     root) does it fall back to the legacy static heuristic
     `workflow_history.anomaly_score([])`, which returns `0.0`. This fallback
     is documented in the function docstring and module docstring.

### `keel/tests/test_event_bus_persistence.py` (new)

Eight regression tests, no skips:

1. 3 publishes through fresh `EventBus(state_root)` objects accumulate
   histories of length 1, 2, 3 (all ids present in the final history).
2. A JSONL file is created under `state_root` with exactly one line per
   publish; subscribers still fire and the reload sees the new event.
3. `EventBus()` with no state root is in-memory only and writes no file.
4. Corrupt JSONL lines are skipped rather than crashing construction.
5. History survives a **fresh Python interpreter** (two `subprocess.run`
   calls: writer then reader).
6. Anomaly detection reacts to real persisted denial events (score 1.0) and
   stays at 0.0 for calm persisted events; `EventBus.anomaly_score()` agrees.
7. Mass file reads in event payloads are detected (score ≥ 0.8).
8. Caller-supplied events and the legacy static fallback keep their old scores.

---

## 3. Change the lead must apply in `capability_registry.py`

`capability_registry.py` is owned by another agent and was **not edited** here.
The EventBus API was designed so the persistence fix is a single line.

### Required one-line change in `_bus` (baseline line 1455)

```diff
 def _bus(p, ctx):
     from .automation import EventBus
-    bus = EventBus()
+    bus = EventBus(ctx.get("state_root"))
     bus.publish(str(p.get("topic", "")), p.get("payload", {}))
     return {"history": bus.history}
```

Exact replacement line:

```python
    bus = EventBus(ctx.get("state_root"))
```

`ctx.get("state_root")` is used (rather than a hard-coded default directory)
so callers that do not provide a state root keep the original in-memory
behaviour. With it, each invoke reloads the accumulated history, appends the
new event, and returns *all* events — not just the latest one.

### Companion one-line change for `fleet.anomaly` (baseline lines 1447–1448)

The new anomaly logic lives in `automation.py`; `_anomaly` must import it and
pass the state root. This is a two-line replacement because the import target
changes:

```diff
 def _anomaly(p, ctx):
-    from .workflow_history import anomaly_score
-    return {"score": anomaly_score(p.get("events", []))}
+    from .automation import anomaly_score
+    return {"score": anomaly_score(p.get("events") or None,
+                                   state_root=ctx.get("state_root"))}
```

With explicit `events` this preserves the existing `fleet.anomaly` contract
(including `test_workflows_e2e.py::test_fleet_workflow` and
`test_product_defects.py::test_fleet_workflow_history_persists_across_restart`).
With no `events`, it scores the persisted bus history.

---

## 4. Commands and results

Targeted + existing related suites (from worktree root):

```
$env:PYTHONPATH = 'keel/src'
python -m pytest -q keel/tests/test_event_bus_persistence.py `
  keel/tests/test_automation.py keel/tests/test_workflow_history.py `
  keel/tests/test_product_defects.py keel/tests/test_workflows_e2e.py `
  keel/tests/test_misc_features.py
```

Result:

```
.................................                                        [100%]
33 passed in 13.62s
```

No tests were skipped; no assertion was weakened or downgraded to a warning.

---

## 5. Scope / limitations

* Only `keel/src/keel/automation.py`,
  `keel/tests/test_event_bus_persistence.py` and this evidence file were
  changed. `capability_registry.py` was read only.
* End-to-end hub verification of `_bus`/`fleet.anomaly` requires the lead to
  apply the two changes in §3; the persistence and anomaly behaviour they
  activate is covered directly by the new tests in this worktree.
* JSONL appends use a single append-mode write per event, adequate for the
  local single-process bus; no cross-process locking scheme was introduced.
