# Group 2 independent backend review — `integration/v6-backend-complete`

Reviewer: independent subagent (did not implement these modules).
Branch: `agent/review-g2` (created from `integration/v6-backend-complete`).
Date: 2026-11-24.

## Scope and method

Reviewed, for each of the five modules, its implementation and its own test file:

- `keel/src/keel/w1_security_backend.py` + `keel/tests/test_w1_security_backend.py`
- `keel/src/keel/x2_orchestration_backend.py` + `keel/tests/test_x2_orchestration_backend.py`
- `keel/src/keel/x3_memory_backend.py` + `keel/tests/test_x3_memory_backend.py`
- `keel/src/keel/x8_backend.py` + `keel/tests/test_x8_backend.py`
- `keel/src/keel/y1_config_backend.py` + `keel/tests/test_y1_config_backend.py`

Per instruction, the full suite was **not** run. Each module's own test file was run in isolation with
`python -c "import sys,pytest; sys.path.insert(0,'keel/src'); raise SystemExit(pytest.main(['-q','keel/tests/test_X.py']))"`:

| Test file | Result |
| --- | --- |
| `test_w1_security_backend.py` | 33 passed |
| `test_x2_orchestration_backend.py` | 23 passed |
| `test_x3_memory_backend.py` | 21 passed |
| `test_x8_backend.py` | 33 passed |
| `test_y1_config_backend.py` | 58 passed |
| **Total** | **168 passed** |

Suspected defects were additionally confirmed with small, standalone Python probes against the real
modules (outputs quoted below as evidence). No network, no full-suite run.

## Verdict summary

| Module | Verdict | One-line reason |
| --- | --- | --- |
| `w1_security_backend.py` | **GENUINE_BACKEND** | Real parsers, stores, policy engines and validators; tests assert concrete outputs/errors. |
| `x2_orchestration_backend.py` | **GENUINE_BACKEND** | Real state machines, parsers, process supervisor and gates; tests assert transitions and errors. |
| `x3_memory_backend.py` | **GENUINE_BACKEND** | Durable JSON/SQLite state, consent gates, crypto, PNG/PDF/SM-2 algorithms; tests assert behavior. |
| `x8_backend.py` | **GENUINE_BACKEND** | Deterministic algorithms (diff, contrast, WCAG, fingerprint, stores) with fail-closed validators. |
| `y1_config_backend.py` | **GENUINE_BACKEND** (contract-only by design) | Real validation/normalisation/planning algorithms; tests assert outputs and typed errors. |

None of the five is a descriptor-only stub. The caveats are about specific defects, not about
missing implementation.

---

## 1. `w1_security_backend.py` — GENUINE_BACKEND

### 1.1 Real observable behavior (not descriptors)

- `PluginScopeTree` (L210–362): mutable registration tree with `_scope_rank` (L182), duplicate
  registration rejection (L234), `replaces` bookkeeping with single-replacement enforcement
  (L240–252), precedence/deeper-scope/later-wins resolution (L264–286), enable/disable/unregister
  (L310–332), and a real dependency-cycle DFS in `validate()` (L334–362).
- `plan_web_launch` / `_is_loopback` / `launch_display` (L373–466): loopback-only host validation,
  port and path validation, SSH env detection, URL construction, `--no-open` propagation, and an
  SSH branch that never opens a browser (L450–466).
- `bundle_digest` / `plan_target` (L486–530): order-independent SHA-256 over renderer sources and
  a shared bundle name for web and desktop targets.
- `BenchmarkStore` (L622–752): on-disk JSON runs, release regex validation, finite non-negative
  metric validation, atomic writes via `_atomic_write_text` (L148), result filtering, averaging
  and layout validation.
- `RgIgnore` (L759–805) + `staged_lint_plan` (L854–875): real glob filtering with negation and
  anchored/dir-only semantics, plus derived ruff/duplicate commands.
- `PortableCIMirror` (L885–961): generates GitHub Actions and GitLab CI YAML and computes job-set
  parity; `validate()` raises on drift.
- `parse_simple_yaml` (L995–1046): hand-written restricted-YAML parser (nested maps, quotes,
  comments, `|` blocks, tab/duplicate-key rejection) + `I18nDocumentStore` locale fallback chain
  (L1088–1128) and HTML escaping in `render_html` (L1120).
- `BuilderInstructionScanner` (L1242–1312): root-confined discovery/reading with size cap and
  CLAUDE.md→AGENTS.md pointer handling.
- `PrivatePluginIndex` (L1319–1411): mtime/size-cache, per-entry validation, duplicate-name
  rejection, root-confined `resolved_path`, and public-topic rejection.
- `redact_feedback` / `build_feedback_bundle` (L1638–1688): token/secret/email/URL/path/IP regex
  passes with counts and forbidden-marker violation reporting.

### 1.2 Test quality

33 tests assert behavior: e.g. scope precedence and cycle detection (`test_w11_*`, L72–110),
host/port/path rejection (`test_w12_rejects_hosts_ports_and_paths`, L122), benchmark round trip and
unsafe-record rejection (`test_w16_*`, L209–241), CI parity/drift (`test_w18_*`, L285–321), YAML
locale fallback and HTML escaping (`test_w19_*`, L323–357), oversize/path-escape and corrupt-index
rejection (`test_w113_*`, `test_w114_*`, L430–495), and redaction assertions
(`test_w117_redaction_and_feedback_bundle`, L564–585). This is output/error assertion, not
existence checking.

### 1.3 Real defects

- **MEDIUM (security, confirmed):** `redact_feedback` allow-list uses `url.startswith(a)`
  (L1666). A look-alike host like `https://docs.keel.example.evil.com/steal` is preserved
  verbatim. Probe: `redact_feedback("see https://docs.keel.example.evil.com/steal and https://docs.keel.example/ok", allowed_urls=["https://docs.keel.example"])` returned both URLs unchanged with `counts == {}`. The default `build_feedback_bundle` adds `docs_site` to `allow`, so the same bypass applies to feedback bundles. Not covered by tests (the test only asserts the exact URL `https://docs.keel.example/guide` is kept).
- **LOW (correctness, confirmed):** `plan_web_launch` percent-encodes each disallowed char with
  `"%%%02X" % ord(m.group())` (L424), which emits invalid 4-digit escapes for non-Latin-1 code
  points: `plan_web_launch(path="/中").url == 'http://127.0.0.1:3080/%4E2D'` (should be UTF-8
  `%E4%B8%AD`). A path that looks percent-encoded to a consumer may be mis-parsed.
- **LOW (robustness):** `stability_info` (L1216) coerces non-string labels with `str(label)`
  instead of rejecting them; a caller-supplied object's `__str__` is invoked and unknown labels
  then fail via a generic error. `VendorPolicy.audit` (L1584–1588) accepts any file whose name
  starts with `license`, following symlinks via `is_file()`/`read_text()` without a root check.

### 1.4 Runtime wiring

No `keel.*` imports (stdlib only). Registered in `keel/backend_hub.py` (`MODULE_FEATURES` L150,
`DISPATCH` L309) and reachable via `backend_hub.invoke` for a small allowlist of pure functions
(`build_feedback_bundle`, `make_help`, `parse_simple_yaml`, `validate_payload`,
`validate_suite_matrix`). Stateful components (`PluginScopeTree`, `BenchmarkStore`, …) are not
exposed through the hub.

### 1.5 Verdict and top 3 findings

**GENUINE_BACKEND.**

1. **MEDIUM — `w1_security_backend.py:1666`** (`redact_feedback`): prefix-based URL allow-list
   preserves `docs.keel.example.evil.com`; secret/PII redaction can be bypassed by choosing an
   allowed-site-prefixed host. Evidence: probe output above; `counts == {}`.
2. **LOW — `w1_security_backend.py:424`** (`plan_web_launch`): invalid `%4E2D` escape for a
   non-Latin-1 path character. Evidence: `'http://127.0.0.1:3080/%4E2D'`.
3. **LOW — `w1_security_backend.py:1216,1584`**: silent `str()` coercion of labels and
   symlink-following license-file discovery (`VendorPolicy.audit`) weaken fail-closed guarantees.

---

## 2. `x2_orchestration_backend.py` — GENUINE_BACKEND

### 2.1 Real observable behavior

- `DiagnosticsLedger` (L291–362): durable open-diagnostic state, key-based resolve, non-empty
  justification, `gate()`/`require_clear()` gating with `GuardError`.
- `CodeActionRouter` (L373–524): LSP-vs-fallback planning, `_validate_changes` root confinement and
  edit-shape validation (L402–431), explicit fallback flagging (L486–492), and application through
  an injected executor (L506–524).
- `TDDRunner` (L568–667) and `BugReproGuard` (L684–765): real phase state machines
  (`red_required → red_confirmed → implemented → complete`, repro confirmation/edit/verify/reopen)
  with evidence records and rejection of fake red/green outcomes.
- `parse_unified_diff` / `added_lines` (L775–836): real hunk parsing into new-file line numbers;
  `CodeReviewEngine` (L856–957) runs pluggable reviewers, validates that comments land on added
  lines, deduplicates, and converts accepted comments to tasks.
- `MergeQueue` (L989–1061): enqueue → preview → mark_green → land with conflict and "land when
  green" gates; a fresh preview resets `ci_green` (L1026) to prevent stale green reuse.
- `summarize` family (L1074–1269): real adapters for pytest, unittest, jest, go, cargo and JUnit
  with bounded failure digests and fallback on parse errors.
- `DependencyUpgradeAssistant` (L1334–1478): offline changelog lookup with sanitized names and
  root confinement, single-flight guard (`_busy`), apply/test/rollback/verify journal with a
  `finally` block.
- `MonorepoGraph` (L1792–1861): cycle detection and transitive dependent expansion.
- `ProcessSupervisor` (L2038–2169): actual `subprocess.Popen` with `shell=False`, argv validation,
  bounded output tail, crash records, stop/restart/crashes.

### 2.2 Test quality

23 tests assert transitions, parsed values and typed errors: diagnostics ledger gating
(L117–141), TDD fake-evidence rejection (L208–232), no edit without failing repro (L234–258),
review-only-added-lines and reviewer isolation (L260–298), merge-queue land gate (L300–333),
runner adapters and truncated logs (L335–381), offline changelog/rollback (L402–443), cycles
(L546–565), and supervisor jobs/crash surface (L609–653). There is a coverage check that all
feature IDs are mentioned (L655–665), but individual tests are behavioral, not existence-only.

### 2.3 Real defects

- **MEDIUM (security, confirmed):** `CodeActionRouter.apply` (L506–524) does **not** re-validate
  the plan it receives. `plan()` confines paths via `_resolve_in_root`, but `apply()` iterates
  `plan["changes"]` and passes `file` directly to `apply_text_edit`. A hand-crafted or persisted
  plan with `../../etc/passwd` is applied. Probe:
  `router.apply({"changes": {"../../etc/passwd": [{"op":"replace","range":{"start_line":1,"end_line":1},"new_text":"x"}]}}, lambda f,e: seen.append(f))`
  returned `{'applied': 1, 'ok': True}` and `seen == ['../../etc/passwd']`. Tests only apply plans
  returned by `plan()`.
- **LOW/MEDIUM (logic, confirmed):** `ExplanationBuilder.explain_change` computes
  `coverage = len(cited) / total` (L1913) while emitting up to five `cited` entries per changed
  line (L1907–1909). With overlapping symbols, coverage exceeds 1.0. Probe with six symbols on
  one line returned `coverage: 5.0, cited: 5, lines_examined: 1`. The test fixture uses
  non-overlapping symbols, so this is untested.
- **LOW (resource leak, confirmed):** `ProcessSupervisor.start` opens the log with
  `stdout=open(log_path, "wb")` (L2075) but never stores the file object in
  `self._jobs[name]["stream"]`; `_close` (L2093–2099) therefore finds `None` and never closes it.
  CPython does not auto-close a file object passed as `stdout` (probe: `f.closed == False` after
  `Popen(...)` and `wait()`). Each `start()`/`restart()` leaks a descriptor.
- **LOW (robustness):** `MigrationAssistant.verify` (L1580) calls `checks.get(...)` on an
  unvalidated argument; `verify(name, None)` raises raw `AttributeError` instead of `BackendError`.
  `ProcessSupervisor.stop` (L2144–2150) can raise `ProcessLookupError` if the process exits
  between `poll()` and `terminate()`.

### 2.4 Runtime wiring

No `keel.*` imports (stdlib only). Registered in `backend_hub.py` (`MODULE_FEATURES` L188,
`DISPATCH` L315) but only `normalize_diagnostic`, `normalize_outcome` and `parse_unified_diff` are
dispatchable; the state machines and supervisor are library-only.

### 2.5 Verdict and top 3 findings

**GENUINE_BACKEND.**

1. **MEDIUM — `x2_orchestration_backend.py:506–517`** (`CodeActionRouter.apply`): applies an
   unvalidated plan; `../../etc/passwd` was passed to the executor unchanged. The root-confinement
   guarantee of `plan()` is not enforced at the application boundary.
2. **LOW/MEDIUM — `x2_orchestration_backend.py:1913`** (`ExplanationBuilder.explain_change`):
   `coverage` can exceed 1.0 (probe: `5.0`) because multiple cited symbols count against one line.
3. **LOW — `x2_orchestration_backend.py:2075,2081–2083`** (`ProcessSupervisor.start`): opened log
   file object is never stored or closed, leaking one descriptor per job start/restart.

---

## 3. `x3_memory_backend.py` — GENUINE_BACKEND

### 3.1 Real observable behavior

- Durable JSON state under `state_root` with `_load`/`save` (L481–503), `_confine` path sandbox
  (L516–527), consent ledger and id generation (L529–537).
- X3.1: approved-folder allow-list, symlink-safe indexing, hashed lexical embeddings, TF/IDF-like
  `_fts_scores` and snippet search (L541–675).
- X3.2: `detect_sensitive` regex spans with overlap resolution (L686–704), a hand-built PDF writer
  `_render_pdf`/`_pdf_escape` (L706–746) and `verify_redacted_pdf` that checks raw bytes plus
  decompressed streams (L764–783).
- X3.3: deterministic receipt parser, SHA-256 dedupe, review queue, SQLite commit and CSV export
  (L796–919), all parameterised SQL.
- X3.4–X3.5: clause/page citation diff (L923–968), a sandboxed AST formula evaluator with cell
  references, ranges, circular detection and six functions (L284–372), error scanning, one-key
  pivot and SVG chart, copy-on-write spreadsheet output with `OVERWRITE` token (L1073–1094).
- X3.6–X3.7: dry-run organiser with collision detection and reversible journals, pHash/SHA-256
  duplicate detection and trash-based safe delete/restore (L1148–1332).
- X3.8–X3.14: HTML→Markdown clipping with link sanitisation, user-registered RSS with DTD/entity
  rejection, SM-2 spaced repetition, Socratic tutor with answer withholding, writing heuristics,
  license-gated third-party checker, CRM/follow-ups, and CSV finance import with network-source
  rejection (L1336–1874).
- X3.15–X3.16: opt-in clipboard with PBKDF2-derived key, HMAC-CTR encryption, integrity tag,
  TTL expiry, per-call consent for agent queries, and consent-gated screenshot-region capture
  with a local PNG codec (L1878–2074).
- `consolidate` (L2078–2110): idempotent cross-store housekeeping with a measured report.

### 3.2 Test quality

21 tests assert concrete outputs and state transitions: approved-folders-only search and FTS
safety (L39–73), redaction/PDF verification including a planted leak (L75–97), receipt parse →
review → CSV and SQL-safety (L99–129), clause diff (L131–144), formula errors and copy-only writes
(L146–174), organiser dry-run/apply/undo/collisions (L176–200), trash/phash (L202–223), clipper
sanitisation and single export (L225–245), RSS/XXE (L247–270), SM-2 and consolidation (L272–293),
tutor no-answer-leak (L295–308), license gate (L310–329), CRM/vault (L331–349), finance CSV/network
rejection (L351–369), clipboard opt-in/consent/encryption/expiry/tamper (L371–400), screenshot
consent (L402–429), consolidation idempotence/durability (L431–448). Strong behavioral coverage.

### 3.3 Real defects

- **MEDIUM (logic, confirmed):** `_FormulaEvaluator.evaluate` (L322–324) rewrites cell references
  with a regex over the *entire* expression, including string literals. As a result the
  advertised `CELL` function cannot be used directly: probe
  `X3Backend._FormulaEvaluator([["1"],["2"]]).evaluate('=CELL("A1")')` raised `X3Error #ERROR!`
  (and `=SUM(CELL("A1"),CELL("A2"))` likewise), while `=SUM(A1:A2)` → `3.0` and `=A1` → `1.0`.
  The test suite exercises only bare refs/ranges, not `CELL("A1")`.
- **MEDIUM (DoS, reasoned from code):** `capture_region` (L2027–2029) builds a PNG with
  `_png_bytes(width, height)` when `image_bytes` is `None`, with no upper bound on `width`/`height`.
  A caller-supplied region such as `{"x":0,"y":0,"width":100000,"height":100000}` makes
  `_png_bytes` allocate ~30 GB (`rows = b"".join(... bytes(rgb)*width for _ in range(height))`,
  L123). The image-bytes branch (L2035) does bound the region; the synthetic branch does not.
- **LOW (error handling, confirmed):** `update_contact` (L1738–1740) assigns caller-supplied
  values into durable state with no type validation; `b.update_contact(id, tags={1,2})` reached
  `save()` and raised `TypeError: Object of type set is not JSON serializable` instead of a typed
  `X3Error`. Related: `purge_expired_clipboard`/`consolidate` call `_parse_iso(e["expires"])`
  directly (L1996, L2096) and will raise on tampered state.

### 3.4 Runtime wiring

No `keel.*` imports (stdlib only). Registered in `backend_hub.py` (`MODULE_FEATURES` L198,
`DISPATCH` L317) only for private pure helpers `_money`, `_word_tokens`, `_slug`, `_embedding`,
`_cosine`; the durable `X3Backend` class and all consent gates are not dispatched through the hub.

### 3.5 Verdict and top 3 findings

**GENUINE_BACKEND.**

1. **MEDIUM — `x3_memory_backend.py:322–324`** (`_FormulaEvaluator.evaluate`): cell-ref
   substitution corrupts string literals; `=CELL("A1")` consistently raises `#ERROR!` despite
   `CELL` being an advertised function. Evidence: probe output above.
2. **MEDIUM — `x3_memory_backend.py:2027–2029`** (`capture_region`): unbounded synthetic PNG
   dimensions permit memory exhaustion from an untrusted region dict.
3. **LOW — `x3_memory_backend.py:1738–1740`** (`update_contact`): unvalidated durable-state writes
   leak `TypeError` from `json.dumps` instead of a typed error. Confirmed: `Object of type set is
   not JSON serializable`.

---

## 4. `x8_backend.py` — GENUINE_BACKEND

### 4.1 Real observable behavior

- Deterministic `canonical_bytes`/`content_hash` (L52–59) underpin every ID and fingerprint; no
  UUID/RNG/import-time side effects.
- Real algorithms: `line_diff` with `SequenceMatcher` opcodes, context hunk merging, old/new line
  numbering and a 2000-line bound (L1097–1140); `render_unified` (L1143); `build_file_preview`
  with range validation (L1169–1188); `resolve_citation` (L1023–1035).
- Fail-closed immutable dataclasses with `__post_init__` validation throughout:
  `PaneZoom`/`LayoutState`/`SavedLayout` (L171–227), `Notification`/`NotificationFilter`
  (L293–338), `ActionableNotification` (L431–452), `KillSwitchCommand` (L579–611 — kill switch
  can never be auto-confirmed), `Citation` (L971–987), `DraftSnapshot` (L1216–1232),
  `UndoableAction` (L1307–1324), `AccessibilityPreferences` (L1517–1534), `DisplayInfo`/
  `WindowRect` (L1592–1637).
- Real services/state machines: `LayoutStore` (L236–263), `ActivityFeed` with unread accounting
  and filters (L341–402), `ThreadIndex`/`build_thread_index` with duplicate ID/seq/tool-call
  detection (L791–850), `compare_sessions` turn diffing (L944–957), `RecoveryStore` latest-wins
  with stale detection (L1258–1293), `UndoStack` bounded FIFO with single-use tokens and
  compensating commands (L1355–1395), `DisplayLayoutStore` with display containment checks
  (L1676–1718).
- Real math: WCAG relative luminance/contrast ratio and AA/AAA thresholds (L1415–1468); token
  import/export delegated to the real `keel.builder_contracts.validate_tokens` (L1471–1502);
  reduced-motion token collapsing (L1560–1576); copy-deck placeholder/coverage validation
  (L1767–1820).

### 4.2 Test quality

33 tests assert computed values, errors and state transitions: X8.1/X8.2 contracts re-verified
(L29–48), zoom quantization and layout validation (L50–83), notification filters/read counts and
fail-closed inputs (L85–152), tray/kill-switch confirmation (L154–181), selection routing (L183–212),
thread outline/jump/timeline (L214–247), session comparison (L249–280), deterministic citations
(L282–311), real diff rendering (L313–346), recovery latest-wins (L348–376), bounded undo FIFO
(L378–411), WCAG thresholds (L413–426), theme round-trip (L428–444), sound/motion defaults
(L446–480), display containment (L482–513), copy deck coverage (L515–544), fingerprint
reproducibility (L546–562), and a stdlib-only/side-effect-free check (L564–574). Excellent quality.

### 4.3 Real defects

- **LOW (immutability contract, confirmed):** `ThemeDocument` is a frozen dataclass but `tokens`
  is a plain nested dict (L1471–1484); the constructor does not copy it. Probe: mutating the
  caller's `tokens["color"]["bg"]` after construction changed `doc.to_dict()["tokens"]` while
  `doc.fingerprint` stayed stale. This contradicts the module's "every output is immutable or
  freshly copied" claim (L20).
- **LOW (validation is descriptor-only, confirmed):** `validate_layout_state` (L266–271) is
  documented as "Re-validate a layout state that was built without constructor checks" but only
  computes `state.fingerprint`. A corrupt object built via `object.__new__` with valid density and
  `panes=("not-a-pane",)` raised raw `AttributeError` from `to_dict()` (not `LayoutError`); with a
  bogus density it likewise raised `AttributeError`. The test only asserts `True` on a valid
  `LayoutState` (test file L70–83).
- **LOW (shared mutable defaults):** module-level mutable `ACTION_CAPABILITIES` (L417) and
  `COPY_DECK` (L1726) are exported in `__all__` (L1837, L1874) and used directly as default
  arguments (L427, L1767, L1789, L1804, L1814). External mutation silently changes the behavior
  of all later calls. No observed misuse inside this module or tests.

### 4.4 Runtime wiring

This is the only module in the group that imports from the real Keel runtime:
`from keel.builder_contracts import DEFAULT_TOKENS, TokenContractError, flatten_tokens,
validate_tokens` (L39–44), used as the single source of truth for token validation (L1477, L1498,
L1565). It is also registered in `backend_hub.py` (`MODULE_FEATURES` L208, `DISPATCH` L319) with
ten deterministic functions dispatchable (`build_thread_index`, `build_tray_snapshot`,
`build_undo_action`, `canonical_bytes`, `check_contrast`, `normalize_zoom`, `render_unified`,
`resolve_citation`, `resolve_preferences`, `validate_copy_deck`). The stateful stores are not
hub-reachable.

### 4.5 Verdict and top 3 findings

**GENUINE_BACKEND** (highest quality of the five; findings are low severity).

1. **LOW — `x8_backend.py:1471–1484`** (`ThemeDocument`): nested `tokens` dict is shared with the
   caller; external mutation changes content but leaves the fingerprint stale. Confirmed by probe.
2. **LOW — `x8_backend.py:266–271`** (`validate_layout_state`): claimed re-validation is a
   no-op fingerprint read; corrupt states raise `AttributeError` rather than a typed
   `LayoutError`, and the test only checks the happy path.
3. **LOW — `x8_backend.py:417,1726,1837,1874`**: exported mutable defaults
   (`ACTION_CAPABILITIES`, `COPY_DECK`) can be globally mutated, silently changing default
   behavior.

---

## 5. `y1_config_backend.py` — GENUINE_BACKEND (contract-only by design)

### 5.1 Real observable behavior

This module deliberately performs validation/normalisation/planning only — no sockets, subprocess
or file writes (docstring L33–39) — but the algorithms are real:

- Shared validators with typed error codes: `_text`/`_blob_text`/`_safe_id`/`_relative_path`/
  `_rooted`/`_contained`/`_int`/`_number`/`_bool`/`_mapping`/`_sequence`/`_url` (L190–397).
  `_url` rejects credentials, non-public IPs, disallowed ports and hosts outside an allow-list.
- `validate_code_script` (L445–458): real static gate (size, line count, unsafe tags, 12 forbidden
  token patterns) and `authorize_code_mode_call` (L494–513) enforces an injected permission gate
  on every nested tool call.
- Skill-advertisement gate (`can_load_skill`/`require_skill`, L529–559), subagent depth/namespace
  and notification rules (L571–638), worktree strategy/permission plans (L687–750), browser tool
  catalog and URL/size validation (L776–836), image-job descriptors with local-provider and
  extension checks (L859–882).
- Managed config precedence/paths (L889–943), update-mode resolution with project-scope
  suppression (L950–983), watcher glob validation (L1002–1016), media/tool-output limit
  resolution and real output clipping with byte/line accounting (L1051–1108), cache warm policy
  and remote opt-in/cost gates (L1124–1165).
- Reference/source parsing with path/repository exclusivity (L1184–1231), skill/instruction
  source URL and traversal handling (L1247–1332), plugin source parsing with exact-version/commit
  pinning and shell-metacharacter rejection (L1362–1438), plugin surfaces and hot-reload planning
  (L1458–1525).
- Idle unload guards (L1539–1561), todo flag filtering (L1572–1585), model override merging with
  output≤context validation (L1602–1638), `propose_config_edit` (L1669–1706) with exact-match
  replacement and unified diff, docs generation with HTML escaping (L1723–1752), install-plan
  per-user/system-dir rejection (L1784–1828), gitleaks allowlist expiry/review checks
  (L1848–1874), topological task ordering (L1885–1902), trademark notice validation
  (L1910–1929).

### 5.2 Test quality

58 tests assert exact outputs and typed errors — e.g. code-mode denial fallback and script-guard
patterns (L30–78), traversal/unsafe IDs (L80–99), depth limits (L112–130), worktree
force/permission (L155–188), browser catalog/URL/size (L190–225), hidden provider/image path checks
(L227–256), managed env traversal (L258–282), update modes (L284–300), watcher patterns
(L310–323), clipping (L331–348), cache opt-in/cost (L350–375), all source parsers and SSRF/
shell-injection rejection (L377–498), manifests/hot reload (L499–527), idle/todo/model overrides
(L529–597), config edit tiers (L598–625), docs escaping (L626–648), install dirs (L650–677),
gitleaks (L678–712) and trademarks (L714–725). Very high quality within the contract scope.

### 5.3 Real defects

- **MEDIUM (security theater / descriptor-only verification, confirmed):**
  `skill_pack_signature_check` (L1273–1285) returns `{"verified": True}` for *any* non-empty
  `signature` string with an allowed algorithm name; it performs no cryptographic verification.
  Probe: `skill_pack_signature_check({"signature":"garbage","algorithm":"ed25519"})` →
  `{'verified': True, 'algorithm': 'ed25519', 'network_used': False}`. The test at
  `test_y1_config_backend.py:418` explicitly locks this in (`"abc"` → verified True), so this is
  an intentional contract convention, not an accidental coding error — but a consumer treating
  `verified` as authenticity would be misled. This is the clearest descriptor-only behavior in the
  group.
- **MEDIUM (security, confirmed):** the Tier-2 config-edit gate in `propose_config_edit` (L1703)
  scans only the unified diff for `_TIER2_RE` matches. A value nested more than three lines below
  its Tier-2 key can be changed without any Tier-2 key appearing in the diff. Probe: changing
  `"OLDVALUE"` → `"NEWVALUE"` inside an `"auth"` block whose key is 5 lines above produced an
  accepted proposal with `changed_keys == ()`, `requires_approval=True` and no `tier2_blocked`
  error. The test (L606–615) only covers a one-line `{"auth": "x"}` case where the key is on the
  changed line.
- **MEDIUM (SSRF guard bypass, confirmed):** `_url` (L373–384) only calls
  `ipaddress.ip_address(host)` on the literal hostname; non-canonical IP spellings fall through
  with `address = None` and are accepted when `allowed_hosts` is empty. Probe:
  `validate_browser_url` accepted `http://0x7f000001/x`, `http://127.1/x` and
  `http://2130706433/x` (verified on Python 3.11, where `ipaddress.ip_address("2130706433")`
  itself raises `ValueError`). Hostnames resolving to private addresses are likewise not
  resolvable in a pure contract, so this check is advisory for any host that actually fetches.
- **LOW (defense-in-depth, confirmed):** `_relative_path` (L260–269) unquotes exactly once;
  `_relative_path("%252e%252e%252fetc%252fpasswd")` returned the literal string
  `%2e%2e%2fetc%2fpasswd`. A downstream consumer that unquotes again would see `../../etc/passwd`.
  `parse_plugin_source` (L1387–1392) validates `git+ssh://` sources only for `..` and the presence
  of `@`; spaces/quotes are not in `_SHELL_INJECTION_RE` (L185). Neither module executes commands,
  so impact depends on the host consumer.

### 5.4 Runtime wiring

No `keel.*` imports (stdlib only). Registered in `backend_hub.py` (`MODULE_FEATURES` L218,
`DISPATCH` L321) for ten pure functions (`build_docs_pages`, `parse_instruction_sources`,
`parse_plugin_manifest`, `parse_plugin_source`, `parse_references`, `parse_skill_sources`,
`resolve_media_limits`, `resolve_tool_output_limits`, `resolve_update_mode`,
`validate_base64_size`). The many plan/validation functions that are not in the dispatch list are
not hub-reachable.

### 5.5 Verdict and top 3 findings

**GENUINE_BACKEND** with a contract-only scope; the verification-shaped functions are the weak
spot.

1. **MEDIUM — `y1_config_backend.py:1273–1285`** (`skill_pack_signature_check`): reports
   `verified=True` with no cryptographic check; test L418 asserts the behavior. A descriptor
   presented as a security verification.
2. **MEDIUM — `y1_config_backend.py:1703`** (`propose_config_edit`): Tier-2 gate inspects only diff
   text; nested value edits more than 3 lines from a Tier-2 key bypass the block (confirmed:
   accepted proposal, `changed_keys == ()`).
3. **MEDIUM — `y1_config_backend.py:373–384`** (`_url`): non-decimal IP spellings
   (`http://0x7f000001/x`, `http://127.1/x`) bypass the non-public-address SSRF guard (confirmed).

---

## Cross-cutting observations

1. **Wiring is real but narrow.** All five modules are registered in `keel/backend_hub.py` and
   reachable through `backend_hub.invoke`, which calls the actual functions (L1364–1390) and is
   described as consumed by `keel.capabilities`. However, only a small allowlist of *pure*
   functions per module is dispatchable. The stateful backends that do the interesting work —
   `PluginScopeTree`, `BenchmarkStore`, `TDDRunner`, `MergeQueue`, `ProcessSupervisor`,
   `X3Backend`, `LayoutStore`, `ActivityFeed`, `RecoveryStore`, `UndoStack` — are library-only and
   not exercised by hub dispatch. Only `x8_backend.py` imports a real runtime module
   (`keel.builder_contracts`).
2. **Tests are behavioral, not existence checks.** All 168 targeted tests pass and generally
   assert outputs, typed errors, state transitions and fail-closed cases. The weak spots found
   above are precisely the paths the tests do not cover (look-alike URLs, hand-crafted plans,
   overlapping symbols, direct `CELL()` calls, unbounded regions, deeply nested Tier-2 edits,
   non-decimal IPs).
3. **No eval/exec, SQL injection or secret leakage found** in the reviewed code paths: the formula
   evaluator uses a whitelisted AST walker; SQL is parameterised; secrets are not echoed in error
   messages; OCR/page text is labelled untrusted and escaped; kill-switch and consent gates fail
   closed. The confirmed issues are logic/validation gaps, not arbitrary-code-execution holes.
