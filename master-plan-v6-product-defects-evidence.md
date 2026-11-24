# Master Plan v6 — Connected-Product Defect Evidence (Agent 21-24)

Worktree: `.local/share/opencode/worktree/final/product-defects`
Branch: `agent/f-product-defects` · Baseline: `cc6240e4bd707b05bfeb650ff57c9e808ab605b1`

All commands below were run from the worktree root with
`$env:PYTHONPATH="keel/src"` (PowerShell).

---

## 1. Baseline (before changes)

```
python -m pytest -q keel/tests/test_e2e_local.py keel/tests/test_e2e_operations.py \
  keel/tests/test_workflows_e2e.py keel/tests/test_concurrency_recovery.py
```

Result: **29 passed in 23.17s** — the existing suite is green, so the defects
below are not caught by the current E2E coverage (they assert `ok=True` and
single-shot outputs only).

---

## 2. Workflows exercised through the real capability hub

All four were driven with `keel.capabilities.invoke(...)` against a temp
state root (`{"cwd": tmp, "state_root": tmp/"state"}`) using a short
exploratory driver (`sys.path.insert(0, "keel/src")`,
`import keel.capability_registry`, then `invoke(...)`), and then pinned as
regression tests in `keel/tests/test_product_defects.py`.

### (a) Cowork — document create → read back → restart → read again

Command: exploratory capability-hub driver (section `=== (a)`).

Observed (before fix):

```
write: True
read1: 'Project Report\nKeel is local-first.\nAmpersand & <tag> test.\nLine5'
read2: 'Project Report\nKeel is local-first.\nAmpersand & <tag> test.\nLine5'
orig : 'Project Report\nKeel is local-first.\n\nAmpersand & <tag> test.\nLine5'
roundtrip equal: False
```

The document persisted across a restart, but its blank line was silently
dropped. This is broken persistence with no error surfaced.

### (b) Code — codemod preview → apply → verify file changed

Observed: preview returned a real unified diff (`-def old` / `+def new`),
preview did not write the file, apply changed it to `def new/new(x)`, and a
second preview correctly reported `changed=False`. The hub path itself works;
a deeper rewrite defect was found and is documented in §3.2.

### (c) Duet — best-of-N with deterministic providers

Observed: with candidates scored `0.1, 0.95, 0.5`, the hub selected `index=1`
value `b` — the highest-scored candidate, not the first. A control regression
test also reverses the candidate order and still expects the highest scorer.

### (d) Fleet — workflow version → history → anomaly → event bus → restart

Observed: `fleet.workflow.version` returned version 1, `fleet.workflow.history`
returned it, `fleet.anomaly` scored 1.0 for 25 destructive events, and the
version snapshot survived a fresh Python process (state file
`workflow-history.json`). The event bus, however, is disconnected and
non-persistent — see §4.1.

---

## 3. Defects found and FIXED (in owned files)

Regression tests were written first and confirmed failing
(**7 failed, 2 passed**), then the fixes below were applied.

Command (before fix):
```
python -m pytest -q keel/tests/test_product_defects.py
```

### 3.1 Cowork DOCX roundtrip silently loses blank lines / trailing newline
- **File:** `keel/src/keel/documents.py`
- **Reproduction:** `test_cowork_doc_roundtrip_survives_restart` — write
  `"Project Report\n\nKeel is local-first. & <tag>\n\nFinal line\n"` via
  `cowork.doc.write`, read back, then read again in a fresh subprocess. Before
  the fix, the read text had no blank lines and no trailing newline.
- **Root cause:** `write_docx` emitted one `<w:p>` per `splitlines()` entry
  (empty paragraphs for blank lines), but `read_docx` skipped every paragraph
  whose text was empty (`if text.strip()`). `splitlines()` also dropped a
  trailing newline.
- **Fix:** `write_docx` normalizes `\r\n`/`\r` and writes one paragraph per
  `split("\n")` line (blank and trailing lines included); `read_docx` keeps
  every paragraph, including empty ones. The roundtrip is now byte-for-byte
  faithful, including across a process restart.

### 3.2 Code `rename_symbol` never renamed attribute references
- **File:** `keel/src/keel/codemod.py`
- **Reproduction:** `test_codemod_rename_renames_attribute_references` — a
  module containing `self.old()` and `svc.old()` was previewed/applied with
  `rename_symbol(old="old", new="new")`. Before the fix, the diff still
  contained `return self.old()` and `result = svc.old()`, despite the
  docstring promising "Rename all Name/**attribute** references".
- **Root cause:** the `Renamer` AST transformer only implemented `visit_Name`,
  `visit_FunctionDef` and `visit_ClassDef`; `ast.Attribute` nodes were never
  inspected, so the `.old` attribute name survived.
- **Fix:** added `visit_Attribute` which rewrites `node.attr` and calls
  `generic_visit` for nested attribute chains. Preview, apply and verification
  now all show `self.new()` / `svc.new()`.

### 3.3 Workflow steps reported fake success
- **File:** `keel/src/keel/workflows.py`
- **Reproductions / root causes / fixes:**
  1. `test_workflow_tool_step_honors_reported_failure` — a tool executor
     returning `{"ok": False, "error": "tool failed"}` was recorded with
     `ok=True`. Same for a `shell` step returning `(text, {"ok": False, ...})`
     (`test_workflow_shell_step_honors_reported_failure`). **Fix:** new
     `_reported_ok()` helper inspects dict / `(text, payload)` returns for an
     explicit `ok` or `error` signal; `tool`, `command` and `shell` steps now
     derive `ok` from it instead of hard-coding `True`.
  2. `test_workflow_map_step_reports_child_failure` — a `map` step whose child
     failed still reported `ok=True`. **Fix:** `map`/`loop` now set
     `ok = all(child["ok"] for sub in results for child in sub)`.
  3. `test_workflow_human_step_without_responder_is_not_success` and
     `test_workflow_human_step_no_answer_is_not_success` — an approval node
     with no responder (or a responder returning `None`, i.e. timeout/no
     answer) substituted `step.default` but marked `ok=True`. **Fix:** such a
     step now sets `result=default`, `defaulted=True`, `ok=False`; only a real
     answer yields `ok=True`. An unanswered approval is no longer a fake
     success.

After the fixes:
```
python -m pytest -q keel/tests/test_product_defects.py
9 passed in 2.74s
```

---

## 4. Defects referred to the lead (files outside my ownership)

### 4.1 Fleet event bus is disconnected and does not survive restart
- **Files to edit:** `keel/src/keel/automation.py` (`EventBus`) and
  `keel/src/keel/capability_registry.py` (`_bus`, lines 1451-1457).
- **Reproduction** (exploratory capability-hub driver, output recorded):
  ```
  publish #1: history=[{'topic': 'task.done', 'payload': {'id': 't1'}, ...}]
  publish #2: history=[{'topic': 'task.done', 'payload': {'id': 't2'}, ...}]
  publish #3: history=[{'topic': 'task.done', 'payload': {'id': 't3'}, ...}]
  state files: []
  ```
  Each of three publishes returns a one-element history: only the event just
  published. Nothing is written under `state_root`. The existing E2E test
  (`test_workflows_e2e.py::test_fleet_workflow`) publishes exactly once and
  only asserts `len(history) == 1`, so it cannot catch this.
- **Root cause:** `_bus` constructs a brand-new `EventBus()` on every invoke;
  `EventBus.history` is an in-process list and the bus takes no `state_root`.
- **Exact fix for the lead:**
  1. Extend `EventBus` in `automation.py` with optional persistence:
     ```python
     class EventBus:
         def __init__(self, state_root=None):
             self._subscribers = defaultdict(list)
             self.path = (Path(state_root) / "eventbus.jsonl") if state_root else None
             self.history = []
             if self.path and self.path.is_file():
                 self.history = [json.loads(line) for line in
                                 self.path.read_text(encoding="utf-8").splitlines()
                                 if line.strip()]
         def publish(self, topic, payload):
             event = {...}
             self.history.append(event)
             if self.path:
                 self.path.parent.mkdir(parents=True, exist_ok=True)
                 with open(self.path, "a", encoding="utf-8") as fh:
                     fh.write(json.dumps(event) + "\n")
             for handler in list(self._subscribers[topic]):
                 handler(event)
             return len(self._subscribers[topic])
     ```
  2. In `capability_registry.py::_bus`, pass the state root and return the
     accumulated history:
     ```python
     bus = EventBus(str(p.get("state_root", ctx.get("state_root", ".keel"))))
     bus.publish(...)
     return {"history": bus.history}
     ```
  3. Wire `fleet.anomaly` to read the same persisted history when the caller
     omits `events`, so "workflow run → event bus → anomaly detection" is one
     connected flow rather than three disconnected capabilities.
  4. Add a regression test asserting that publishing t1 then t2 returns a
     history containing **both** and that a fresh `EventBus(state_root)` sees
     both after a restart.

### 4.2 Duet best-of-N hub drops the scoring evidence
- **File to edit:** `keel/src/keel/capability_registry.py` (`_bon`, lines
  1314-1321).
- **Reproduction** (exploratory capability-hub driver):
  ```
  hub result: {'index': 1, 'value': {'score': 0.9, 'value': 'b', 'evidence': 'tested'}}
  module result has score/evidence: 0.9 'tested'
  ```
  `keel.best_of_n.best_of_n` returns a `Candidate` carrying `score` and
  `evidence`, but the hub returns only `index` and `value`. A caller cannot
  audit *why* a candidate won, so "selected by real scoring" cannot be
  verified through the hub.
- **Exact fix:** return the full candidate:
  ```python
  return {"index": result.index, "value": result.value,
          "score": result.score, "evidence": result.evidence}
  ```
  (additive; no existing assertion breaks).

### 4.3 Cancellation
No owned module exposes a cancellation API, and `runner.py` has no cancel
path, so there was no reproducible "cancellation that does not cancel" defect
in scope. Flagged for the lead if a cancellation surface is planned.

---

## 5. Final verification

```
python -m pytest -q \
  keel/tests/test_product_defects.py keel/tests/test_documents.py \
  keel/tests/test_codemod.py keel/tests/test_workflows.py \
  keel/tests/test_workflow_nodes.py keel/tests/test_best_of_n.py \
  keel/tests/test_notebook.py keel/tests/test_capabilities_integration.py \
  keel/tests/test_no_fake_success.py keel/tests/test_e2e_local.py \
  keel/tests/test_e2e_operations.py keel/tests/test_workflows_e2e.py \
  keel/tests/test_concurrency_recovery.py
```
**73 passed in 68.33s.**

Additional related suites:
```
python -m pytest -q keel/tests/test_document_endpoints.py \
  keel/tests/test_e2e_milestone_6b.py keel/tests/test_capability_ui.py \
  keel/tests/test_capability_cli_tui.py keel/tests/test_vertical_slice.py \
  keel/tests/test_reliability_e2e.py keel/tests/test_cli_e2e.py
```
**27 passed in 49.98s.**

No assertions were weakened; no failure was converted to a skip.
