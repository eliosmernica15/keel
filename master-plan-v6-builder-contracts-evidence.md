# Addendum 3 — Builder-process / UI-contract P0 set (X10.1, X10.2, X10.4, X6.7, X8.1, X8.2): implementation evidence

Branch: `agent/a9-docs` (worktree `.../worktree/addenda/a9-docs`).
Baseline: `f2c0fe6` (read-only; no existing file was edited).
Source of requirements: `PLAN-INDEX.json` (canonical 865-row registry) → the six
**not_started P0** rows X10.1, X10.2, X10.4 (Section J, process and builder
control), X6.7 (Section F, developer platform) and X8.1, X8.2 (Section H,
UI/UX depth). Requirement text is corroborated by
`Keel_Plan_v5_Addendum_3_Gaps_and_Advanced.md` and by `DECISIONS.md` D-034 for
the G1–G7 stop-list mirror.

This workstream is **additive and honest**: no existing source file, test,
settings schema, UI stylesheet or registry row was edited. The canonical
implementation lives in one new module and is exercised by one new permanent
contract-regression test file. Integration into the live runtime is a separate
lead decision (seams listed at the end).

## Files owned

| File | Purpose |
| --- | --- |
| `keel/src/keel/builder_contracts.py` | Canonical implementation of all six P0 contracts. Stdlib only; no network, subprocess, filesystem I/O, SQL execution, credential value or import-time side effect. No uuid/rng: all ids/fingerprints are deterministic SHA-256 prefixes. |
| `keel/tests/test_builder_contracts.py` | 24 permanent contract tests, including edit-distance/suggestions, token validation, stop-list completeness, JSONC line/column, lint and determinism guarantees. |
| `master-plan-v6-builder-contracts-evidence.md` | This document. |

## Contracts implemented

| ID | Registry requirement | Primary symbols | Tests |
| --- | --- | --- | --- |
| X10.1 | Definition-of-done template per row: code path, test path, e2e run id, docs updated, license/notice check, rollback note | `DOD_FIELDS`, `DOD_FIELD_LABELS`, `DefinitionOfDone`, `DoDValidation`, `dod_template`, `validate_dod` + `DoDError` | `test_dod_template_has_all_six_required_fields`, `test_dod_validation_and_markdown_render`, `test_dod_requires_feature_id_and_reports_missing_sections` (3) |
| X10.2 | Provenance file per module: spec source, any copied snippet with its license, reviewer | `CopiedSnippet`, `ProvenanceRecord`, `build_provenance`, `validate_provenance`, `render_provenance` + `ProvenanceError` | `test_provenance_record_round_trip_and_fingerprint`, `test_render_provenance_is_deterministic_and_machine_readable`, `test_provenance_rejects_missing_license_spec_source_or_reviewer` (3) |
| X10.4 | Builder stop list: owner-paused actions mirrored from G1–G7 plus destructive repo actions, as a machine-readable file the builder must check | `Gate`, `GATE_TITLES`, `GATE_DESCRIPTIONS`, `StopListEntry`, `STOP_LIST` (14 entries), `STOP_MATCH_TERMS`, `find_stop_entry`, `check_action`, `assert_not_paused`, `stop_list_document`, `stop_list_json`, `validate_stop_list` + `StopListError` | `test_stop_list_mirrors_all_seven_owner_gates`, `test_stop_list_is_complete_and_fail_closed`, `test_stop_list_document_is_deterministic_machine_readable_file`, `test_check_action_pauses_gates_and_destructive_repo_actions` (4) |
| X6.7 | Config validation with “did you mean” suggestions, line/column errors for JSONC, and `keel config explain <key>` | `edit_distance`, `did_you_mean`, `strip_jsonc`, `jsonc_key_positions`, `KNOWN_CONFIG_KEYS`, `CONFIG_KEY_DOCS`, `ConfigDiagnostic`, `ConfigValidation`, `ConfigExplanation`, `validate_config_text`, `explain_key` + `ConfigContractError` | `test_edit_distance_known_values`, `test_did_you_mean_ranks_deduplicates_and_limits`, `test_validate_config_text_reports_jsonc_key_typo_with_line_column`, `test_validate_config_text_reports_json_decode_line_column`, `test_config_explain_found_and_suggestions` (5) |
| X8.1 | Local component catalog showing every component in every state against Keel tokens, for visual regression | `ComponentState`, `ComponentDescriptor`, `LOCAL_COMPONENT_CATALOG` (9 components / 37 variants), `CatalogValidation`, `validate_catalog`, `catalog_manifest`, `render_catalog_json` | `test_catalog_covers_every_component_in_every_declared_state`, `test_catalog_manifest_resolves_tokens_deterministically` (2) |
| X8.2 | `tokens.json` as only source of color/type/spacing/radius/motion; lint rule rejects hard-coded values | `TOKEN_CATEGORIES`, `DEFAULT_TOKENS` (29 tokens), `TokenDiagnostic`, `TokenValidation`, `flatten_tokens`, `validate_tokens`, `tokens_json`, `HardcodedValue`, `LintReport`, `lint_source`, `assert_no_hardcoded_values` + `TokenContractError` | `test_default_tokens_pass_validation`, `test_token_validation_rejects_missing_category_bad_name_and_empty_value`, `test_tokens_json_is_canonical_and_deterministic`, `test_lint_rejects_hardcoded_values_with_line_column_and_suggestion`, `test_assert_no_hardcoded_values_raises_on_violation` (5) |

Cross-cutting (2 tests): `test_all_fingerprints_are_reproducible`,
`test_module_has_no_runtime_side_effects_or_external_dependencies`.
**Total: 24 tests, all passing.**

## Design decisions worth the lead's attention

1. **The definition of done is a checklist, not a promise (X10.1).**
   `dod_template(feature_id)` returns a fully blank six-field template;
   `validate_dod` reports exactly which sections are still missing and
   `render_markdown` renders `[x]` / `[ ]` boxes. Nothing can claim `complete`
   until every one of code path, test path, e2e run id, docs updated,
   license/notice check and rollback note is filled. A bad `feature_id` is
   unconstructable.
2. **Provenance is per module and rejects unknown licenses (X10.2).**
   `ProvenanceRecord` requires spec source, reviewer and a concrete
   license/notice for every `CopiedSnippet` (`unknown`, `n/a`, `tbd` and empty
   values are refused). `render_provenance` emits stable JSON or Markdown, so
   the file can be regenerated and diffed rather than hand-maintained.
3. **The stop list is fail-closed and complete (X10.4).** The 14 entries are
   the seven verbatim owner gates from `DECISIONS.md` D-034 plus seven concrete
   destructive repo actions (force-push, hard reset, destructive clean,
   worktree removal, deleting branches/tags/releases, credential/deploy-key
   rotation, disabling CI/release protection). A `StopListEntry` **cannot be
   constructed** with `paused=False` or `requires_owner_approval=False`.
   `validate_stop_list` proves G1–G7 appear exactly once and that the
   destructive category is present. `check_action` matches by exact id first
   and then by specific phrase; `assert_not_paused` raises `StopListError`.
   `stop_list_json()` is the machine-readable `builder-stop-list.json`.
4. **Y6.4 was intentionally NOT implemented (owner gate conflict).** Registry
   row Y6.4 is “repo visibility: Public, 0 stars/forks” and depends on gate G1.
   `DECISIONS.md` D-034 leaves G1 **pending**; the repository's private-source
   requirement and `AGENTS.md` (“never … change repo visibility without
   explicit owner approval”) make any action on this row owner-gated. Making
   the repo public would directly violate the owner's private-repo
   requirement, so the row stays `not_started` and **no visibility change was
   performed**. The stop list above records G1 as a paused action so the
   builder checks it before ever acting. This is a deliberate exclusion, not
   an omission or a claim of verification.
5. **Suggestions and locations are deterministic (X6.7).** `edit_distance` is
   a rolling-row Levenshtein implementation; `did_you_mean` scores
   case-insensitively, deduplicates, sorts by `(distance, candidate)`, honours
   `limit`, and never returns the input itself. `strip_jsonc` preserves
   line/column by replacing comments with whitespace, and
   `jsonc_key_positions` records the original `(line, column)` of each key, so
   a typo such as `"thme"` is reported at line 3, column 3 with the suggestion
   `theme`. JSON decode failures keep `JSONDecodeError.lineno/.colno`.
   `explain_key` is the pure form of `keel config explain <key>`, with
   `ConfigExplanation.render()` producing the user-facing line.
6. **Tokens are the only style source, and hard codes are rejected (X8.2).**
   `validate_tokens` enforces exactly the five categories
   color/type/spacing/radius/motion, safe token names and non-empty string
   values; `tokens_json()` is canonical sorted-key output. `lint_source`
   scans UI source for hex/rgb colors, `px`/`rem`/`em` lengths and `ms`/`s`
   durations, reports original line/column, and suggests the exact token whose
   value matches (preferring the same category) or a category default.
   `assert_no_hardcoded_values` fails closed. No UI file was modified.
7. **The component catalog is a token-only manifest (X8.1).** Stories are
   represented as `ComponentState` × `ComponentDescriptor` data with 37
   component/state variants. `validate_catalog` rejects unknown token refs,
   duplicate components, duplicate states and a missing default state;
   `catalog_manifest` resolves every ref through `flatten_tokens()` so the
   output contains **resolved token values but no hard-coded style**. A
   Storybook/Ladle viewer was deliberately not introduced: that would add a
   JS tool with its own license review and a runtime dependency, breaking the
   local-first/free-only and additive constraints. The deterministic JSON
   manifest is the free, stdlib-only basis a lead can feed to a visual
   regression harness — see the seam below.

## Test results

Command (from worktree root — the established pattern for this addenda work):

```
python -c "import sys,pytest; sys.path.insert(0,'keel/src'); raise SystemExit(pytest.main(['-q','keel/tests/test_builder_contracts.py']))"
```

Result: **`24 passed`** in 0.87–1.02 s across three consecutive runs.
`python -m py_compile keel/src/keel/builder_contracts.py keel/tests/test_builder_contracts.py`
→ clean. Python 3.11.9, pytest 9.0.2. No existing test file was modified.

Full-suite context (honest): the same command against all of `keel/tests`
gave `2555 passed, 51 skipped, 1044 subtests passed, 22 failed`. Those 22
failures are unrelated to this batch — they are missing release artifacts
(`release/RELEASE-MANIFEST.json`, SHA256SUMS), registry/hash drift tests, and
pre-existing policy/permission/tool-registry/session-export failures.
`git status` confirms this batch added only the two additive Python files;
none of the failing tests imports `keel.builder_contracts`. This batch does
not claim those failures were fixed.

Note on invocation: running `python -m pytest -q` from inside `keel/` resolves
`keel` to a globally installed copy in the parent workspace, so the root-level
`sys.path.insert(0,'keel/src')` command above is the correct way to exercise
this worktree.

## Exact integration seams needed by the lead

This module is deliberately not wired into the live runtime or registry. To
adopt it, a lead would:

- **X10.1/X10.2:** generate a `DefinitionOfDone` and a `ProvenanceRecord` per
  registry row/module and commit the rendered files; require `validate_dod`
  to pass before flipping a row to `verified`.
- **X10.4:** write `stop_list_json()` to `builder-stop-list.json`, have the
  builder call `assert_not_paused(action)` on each planned action, and keep
  `G1` paused until the owner explicitly approves (Y6.4 stays `not_started`).
- **X6.7:** feed `validate_config_text` from the settings loader and route
  `keel config explain <key>` through `explain_key().render()`; replace the
  local `KNOWN_CONFIG_KEYS` set with the real schema's key set.
- **X8.2:** publish `tokens_json()` as `tokens.json` and run `lint_source` in
  CI over `site/ui/` and `desktop-app/`; this batch does not modify those
  files, so any existing hard-coded values must be migrated separately.
- **X8.1:** render `render_catalog_json()` into a local viewer (Storybook or
  Ladle, after license review) for visual regression snapshots.

Commit: see `git log -1` on `agent/a9-docs`. No push, publish or repo-visibility
change was performed.
