# D6 builder-constitution rows — backend implementation evidence

Branch: `agent/b1-d6` (worktree `.../worktree/backend/b1-d6`).
Baseline: `982335d` (`Add remaining-backend feature analysis (430 not-started rows classified by prefix)`).
Requirement source: `PLAN-INDEX.json` (865-row canonical registry) → all **25** `D6.*` rows,
every one `status: not_started`, `priority: P1`, section 7
("Builder constitution (rules to give the AI builder, from DS-AGENTS)") of
`Keel_Plan_v5_Addendum_6_DeepSeek_Harness_Full_Teardown.md`.

This workstream is **additive**: no existing source file, test, settings schema,
UI stylesheet or registry row was edited. The canonical implementation is one
new stdlib-only module; one new permanent test file exercises it. The delivery
commit SHA is reported in the subagent's final message (`git rev-parse HEAD`
in the worktree).

## Files owned

| File | Purpose |
| --- | --- |
| `keel/src/keel/d6_reliability_backend.py` | Canonical backend for every BACKEND-classified D6 row. Stdlib only; no network, subprocess, filesystem I/O, SQL, credentials, uuid/rng or import-time side effects. Source checks operate on caller-supplied text, so results are reproducible on macOS/Linux/Windows. All ids/fingerprints are SHA-256 prefixes of canonical JSON. |
| `keel/tests/test_d6_reliability_backend.py` | 35 permanent contract tests: happy path + adversarial rejection for every implemented feature, plus cross-cutting stdlib/determinism checks. |
| `master-plan-v6-d6-backend-evidence.md` | This document. |

## Classification of all 25 D6 rows

"BACKEND" means the row has a deterministic, machine-checkable behaviour that
can be implemented and tested in a stdlib module without editing existing files
or depending on owner/GitHub/CI actions. "EXCLUDED" rows are genuine rules, but
they are human workflow, review policy or external-tool conventions with no
local runtime artifact to implement honestly.

| ID | Full requirement (abridged) | Class | Outcome / primary symbols | Tests |
| --- | --- | --- | --- | --- |
| D6.1 | Public API changes update every consumer and are recorded in an upgrade guide; SQLite uses monotonic `SCHEMA_VERSION` | BACKEND | IMPLEMENTED — `ChangeKind`, `ApiChange`, `ApiChangeRecorder`, `check_upgrade_guide`, `SchemaVersion`, `assert_monotonic`, `scan_schema_version` + `ApiStabilityError`/`SchemaVersionError` | 3 |
| D6.2 | Plugins attach to documented extension points; loop changes require an architecture-doc update | EXCLUDED | Architecture-placement and doc-sync **review convention**. Whether a change actually "moves the loop" is a human judgment; no local runtime artifact. The generic `DocCoverageChecker` (D6.13) can encode the loop→`architecture.md` mapping when a lead declares it, but the decision itself is not backend code. | 0 |
| D6.3 | Typed events with documented mode and payload; closed unions end in `assert_never`; extensible unions have a documented default | BACKEND | IMPLEMENTED — `EventMode`, `UnionStyle`, `EventSpec`, `EventCatalog`, `EventDispatch`, `dispatch`, `assert_never`, `render_mode` + `EventUnionError` | 2 |
| D6.4 | Defaults applied in explicit `resolve(request) -> Spec`, never a hidden `or default` inside `run()` | BACKEND | IMPLEMENTED — `Request`, `Spec`, `resolve`, `run`, `find_hidden_defaults`, named `DEFAULT_*` constants + `ResolutionError` | 2 |
| D6.5 | No hardcoded tunables in plugins: deployment-varying values are validated config; protocol/security constants allowlisted | BACKEND | IMPLEMENTED — `PluginTunables`, `validate_plugin_config`, `PROTOCOL_CONSTANTS_ALLOWLIST`, `MagicNumberFinding`, `lint_plugin_source`, `assert_no_magic_numbers` + `PluginConfigError` | 2 |
| D6.6 | Misconfiguration fails loud at load; never silently skip a missing referent | BACKEND | IMPLEMENTED — `ReferenceRegistry`, `load_with_references`, `LoadedConfig` + `MisconfigurationError` (unknown `$ref:` aborts the whole load) | 2 |
| D6.7 | Opaque cross-boundary ids are branded `NewType`s, never bare `str` | BACKEND | IMPLEMENTED — `SessionId`/`RequestId`/`PluginId`/`SnapshotId`, `brand_id`, `audit_id_annotations` + `TypedIdError` | 2 |
| D6.8 | Trust types in-process; validate at parser/config, queue, model/tool JSON, durable file, wire and worker boundaries only | BACKEND | IMPLEMENTED — `Boundary`, `EXTERNAL_BOUNDARIES`, `TrustedValue`, `trust`, `ValidatorSpec`, `BoundaryRegistry.validate` + `BoundaryError` (unknown boundaries fail closed) | 2 |
| D6.9 | No new `Any`/`object` casts beyond the recorded baseline; replace with typed values or validation | BACKEND | IMPLEMENTED — `CastRecord`, `CastBaseline`, `CastGateReport`, `scan_cast_calls` (AST + `# reason:`) + `CastBaselineError` | 1 |
| D6.10 | Source plane vs artifact plane never mixed; tests resolve to source and gates declare built-output dependencies | BACKEND | IMPLEMENTED — `Plane`, `classify_path`, `GateDeclaration`, `ImportGate`, `assert_source_import` + `PlaneError` | 2 |
| D6.11 | Structured typed errors (`KeelError` with code); stop on untrusted state/unknown outcome; empty `except` names error and why and has one statement | BACKEND | IMPLEMENTED — `KeelError` (22 stable codes), 22 typed subclasses, `all_error_codes`, `fail_on_untrusted`, `fail_on_unknown_outcome`, `ExceptFinding`, `audit_except_handlers`, `assert_handled_excepts` | 3 |
| D6.12 | Local non-restating comments; docstrings with params/returns on public exports; word budgets | BACKEND | IMPLEMENTED — `DOCSTRING_WORD_BUDGETS`, `audit_docstrings`, `assert_documented`, `find_restating_comments` + `DocstringError` ("non-restating" is checked as literal code-restating comments; semantic quality stays a review matter) | 2 |
| D6.13 | Docs accompany code: update README/docstrings in the same change | BACKEND | IMPLEMENTED — `DocRule`, `DEFAULT_DOC_RULES`, `DocCoverageChecker.check`, `assert_docs_in_sync`, `DocCoverageReport` + `DocSyncError` | 1 |
| D6.14 | Tests describe behavior, not "correctness"; obsolete behavior changes with its tests and an explanation | EXCLUDED | Test-authoring/review discipline. Test names and the explanatory narrative are human-authored; no deterministic runtime predicate exists for "describes behavior". No runtime artifact. | 0 |
| D6.15 | Non-trivial user/model-visible change updates a keyless recorded-session snapshot; fixtures replay on macOS/Linux/Windows; fix fixtures, not normalizers | BACKEND | IMPLEMENTED — `assert_keyless`, `SnapshotFixture`, `SnapshotRegistry.replay`/`replay_all`, `assert_no_normalizers`, `assert_snapshot_updated`, `ALL_PLATFORMS` + `SnapshotError` (exact equality; no normalisation) | 3 |
| D6.16 | Both SDKs project the loop; loop/lifecycle/event-map changes update Python and TypeScript expected outputs in the same change | BACKEND | IMPLEMENTED — `SdkProjection`, `validate_projection`, `SdkProjectionValidator`, `assert_projection_in_sync`, `projection_manifest`, `CORE_LIFECYCLE` + `SdkProjectionError` | 2 |
| D6.17 | Agent Notes (ADR-like) only for durable rationale; archived notes frozen and never current authority | EXCLUDED | Documentation-governance convention for human-authored notes. A dataclass cannot enforce an author's decision rationale or the freeze policy of a markdown archive; no backend surface consumes such notes. | 0 |
| D6.18 | Prefer maintained dependencies over hand-rolling when owned code and tests are deleted | EXCLUDED | Engineering judgment requiring dependency lifecycle/security evaluation and owner approval; no deterministic local check. (D6.19 implements the related *vendoring pin* mechanics.) | 0 |
| D6.19 | Vendored packages are pinned source copies with an upstream-SHA manifest; changes require manifest updates; local modifications are logged | BACKEND | IMPLEMENTED — `LocalPatch`, `VendoredPackage`, `VendorManifest.check_tree_sha`/`changes_require_manifest_update`/`validate`, `render_vendor_manifest` + `VendorManifestError` | 2 |
| D6.20 | Run only relevant checks locally; CI owns exhaustive coverage; don't repeat a passing check for commit/push | EXCLUDED | Builder workflow policy (which commands an agent runs), not a runtime capability. Cannot be enforced from inside the application backend. | 0 |
| D6.21 | PR hygiene: one `kind/*` label, all material `area/*` labels, force-with-lease rewrites, PR description template | EXCLUDED | GitHub-side/owner workflow. Labels, push flags and PR templates require an external GitHub integration and owner-controlled branch protection; nothing to implement in a local stdlib module. | 0 |
| D6.22 | TODO markers by urgency: `FIXME` blocks release, `TODO` soon, `XXX` someday | BACKEND | IMPLEMENTED — `MarkerUrgency`, `MARKER_PATTERN`, `MarkerFinding`, `scan_markers`, `release_gate`, `assert_release_ready` + `MarkerError` | 1 |
| D6.23 | Read defensive-patterns doc before touching package surfaces, remote services, client state, sessions, lifecycle/concurrency/subprocess/teardown code | EXCLUDED | Reader discipline for the human/agent; no runtime API. A "doc was read" flag would be fake success, which this workstream refuses to emit. | 0 |
| D6.24 | Strict typing everywhere; every remaining dynamic type explains why | BACKEND | IMPLEMENTED — `JustifiedDynamic` (concrete non-generic reason required), `TypingFinding`, `TypingAudit.audit`/`assert_strict` + `TypingAuditError` | 1 |
| D6.25 | Machine-checkable invariants in an executed top-level gate; each gate proven to reject an invalid case; narrow justified exceptions | BACKEND | IMPLEMENTED — `InvariantGate.probe`, `GateProbe`, `GateRegistry.probe_all`/`assert_proven`, `GateException` (rejects `global` scope), `top_level_gate`, `GateReport` + `GateError` | 1 |

**Tally: 18 BACKEND rows implemented, 7 EXCLUDED (process/external-tool
conventions), 0 rows claimed without evidence.** 34 feature tests + 1
cross-cutting test = **35 tests, all passing.**

## Design decisions worth the lead's attention

1. **Typed errors are the backbone (D6.11).** `KeelError(code, message,
   details)` has 22 subclasses with stable `D6.x.*` codes and a machine-readable
   `to_dict()`. `all_error_codes()` proves codes are unique and namespaced.
   `fail_on_untrusted` / `fail_on_unknown_outcome` stop dependent work instead
   of inventing a result. The empty-`except` gate uses `ast`, not a regex: a
   single `pass`/`...` body is legal only when the `except` line's comment names
   the caught type and states `why:` or `because`; a bare `except` is always
   rejected.
2. **Gates test themselves (D6.25).** Every `InvariantGate` carries a valid and
   an invalid case; `probe()` requires accept-valid AND reject-invalid (a raise
   counts as rejection). `top_level_gate` runs all probes; `GateException`
   refuses `scope == "global"`, so exceptions must be narrow.
3. **Keyless snapshots use exact equality (D6.15).** `assert_keyless` rejects
   forbidden keys (`timestamp`, `session_id`, `uuid`, absolute paths, …) and
   volatile values (ISO time, UUID, absolute POSIX/Windows paths). Replay never
   normalises; `assert_no_normalizers` rejects `normalize_*`/`scrub_*` helpers,
   so fixture drift must be fixed in the fixture.
4. **Source/artifact planes are declared, not guessed (D6.10).**
   `classify_path` recognises `dist/`, `build/`, `release/`, `node_modules/`,
   `site-packages/`, `__pycache__/`, `.pyc/.so/.dll/.dylib/.whl`. A gate that
   imports an artifact without declaring an `artifact_dependency` fails closed.
5. **Boundaries are explicit (D6.8).** Only six external boundaries get
   validators; in-process values must be wrapped with `trust()` and are marked
   as trusted in the report. Unknown boundaries and malformed payloads raise.
6. **No hidden defaults (D6.4).** `resolve()` applies each default under an
   explicit `if is None`, records the applied field names on `Spec`, and
   `run()` refuses an unresolved `Request`. `find_hidden_defaults` detects
   `x or <fallback>` inside any function named `run`.
7. **Exclusions are deliberate, not omissions.** D6.2, D6.14, D6.17, D6.18,
   D6.20, D6.21 and D6.23 are workflow/review/external-tool rules. Emitting a
   boolean "rule followed" for them without an observable runtime event would
   be fake success; they are documented instead. The generic doc-coverage and
   marker/audit gates can be extended by a lead with declared rules if desired.

## Test results

Command (from the worktree root, established pattern for addenda work):

```
python -c "import sys,pytest; sys.path.insert(0,'keel/src'); raise SystemExit(pytest.main(['-q','keel/tests/test_d6_reliability_backend.py']))"
```

Results (two consecutive runs):

```
...................................                                      [100%]
35 passed in 6.45s
```

```
...................................                                      [100%]
35 passed in 6.65s
```

Additional checks:

```
python -m py_compile keel/src/keel/d6_reliability_backend.py keel/tests/test_d6_reliability_backend.py
→ clean (no output)

python -c "import sys; sys.path.insert(0,'keel/src'); import keel.d6_reliability_backend as d; print('OK', len(d.__all__), len(d.all_error_codes()))"
→ OK 135 22
```

Environment: Python 3.11.9, pytest 9.0.2, Windows. The cross-cutting test parses
the module AST and proves the import set is stdlib-only
(`ast/fnmatch/hashlib/io/json/re/tokenize/dataclasses/enum/typing`) with no
`open/exec/eval/urlopen/Popen` call, and that fingerprints/errors are stable.
No existing test file was modified, and no registry row status was changed.

## Integration seam (separate lead decision)

The module is additive and does not rewire Keel's runtime. To adopt a row,
import the relevant symbol from `keel.d6_reliability_backend` in the
corresponding top-level gate or loader (e.g. `assert_release_ready` in the
release gate, `ImportGate` in the test harness, `DocCoverageChecker` in CI).
Row statuses in `PLAN-INDEX.json` remain `not_started` until a lead verifies
that integration in the live application.
