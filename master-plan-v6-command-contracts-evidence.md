# Addendum 5 — Command / slash-command contracts (W5.x P0): implementation evidence

Branch: `agent/a6-w5` (worktree `.../worktree/addenda/a6-w5`)
Baseline: `4f64b8e` (read-only).
Source of requirements: `PLAN-INDEX.json` → `features[]`, the four
**not_started P0** W5.x rows (W5.1, W5.2, W5.3, W5.4; milestone M7, source
`Keel_Plan_v5_Addendum_5_DeepSeek_Harness_and_Deep_Reads.md`, section 3.4
`[T:OC-CMD]`). Also cross-checked against `Keel_Master_Plan_v6.md`,
`REMAINING-WORK-MATRIX.md`, `P0-BATCHES.md` and `parity.json`.

This workstream is **additive**: no existing source file, test, registry or
artifact was edited. `keel/commands.py`, `keel/tests/test_slash_commands.py`,
the CLI and every pre-existing module are untouched. The canonical
implementation is a new module exercised by a new, permanent contract-regression
test file. Integration into the live runtime is a separate lead decision
(exact seams listed at the end).

## Files owned

| File | Purpose |
| --- | --- |
| `keel/src/keel/command_contracts.py` | Canonical implementation of all four W5.x contracts. Stdlib only; pure parser/descriptor layer — no subprocess, no file reads or writes, no network, no command execution. |
| `keel/tests/test_command_contracts.py` | 18 permanent contract tests, grouped by registry ID. |
| `master-plan-v6-command-contracts-evidence.md` | This document. |

## Contracts implemented

| ID | Registry requirement | Primary symbols | Tests |
| --- | --- | --- | --- |
| W5.1 | Markdown or JSON command definitions; nested folders become `/team/review`; global vs project; project overrides global; nearer overrides ancestor; custom may replace built-in; hot reload | `CommandSource`, `CommandDescriptor`, `CommandRegistry.build`, `_precedence_key`, `command_id_from_path`, `assert_contained_command_path`, `is_contained_command_path`, `hot_reload`, `RegistryReload` | `test_nested_paths_become_slash_command_ids`, `test_path_containment_for_command_files`, `test_project_overrides_global_and_nearer_overrides_ancestor`, `test_custom_replaces_builtin_and_precedence_is_deterministic`, `test_hot_reload_is_content_addressed` (5) |
| W5.2 | Frontmatter `description`, `agent`, `model`, `subagent` (true/false/omit); legacy alias `subtask`; typed validation errors | `parse_frontmatter`, `parse_json_command`, `_yaml_scalar`, `_as_bool`, `_resolve_subagent`, `CommandValidationError`, `CommandParseError` | `test_frontmatter_description_agent_model_subagent_true_false_omit`, `test_legacy_subtask_alias_maps_to_subagent`, `test_frontmatter_validation_errors_are_typed`, `test_json_command_definition_and_parse_errors` (4) |
| W5.3 | `$ARGUMENTS`, positional `$1..$n` with quote grouping; last placeholder takes the rest; missing = empty; fallback appends args | `tokenize_arguments`, `substitute_arguments`, `ArgumentRender`, `ArgumentParseError`, `_PLACEHOLDER_RE` | `test_tokenize_arguments_quote_grouping`, `test_arguments_and_positional_placeholders`, `test_last_placeholder_takes_the_remainder_and_missing_is_empty`, `test_fallback_appends_arguments_when_no_placeholder`, `test_no_shell_interpolation_or_recursive_expansion` (5) |
| W5.4 | Shell-injection markers (bang + backtick + command + backtick): output inserted into the prompt, explicit approval required; runs outside permission flow in opencode — Keel keeps it gated | `parse_shell_descriptors`, `ShellCommandDescriptor`, `PermissionGate`, `permission_gate_for`, `render_shell_output`, `ShellInsertion`, `render_command_prompt`, `RenderedPrompt`, `ShellApprovalError` | `test_shell_descriptor_and_permission_gate`, `test_shell_output_insertion_requires_explicit_approval`, `test_no_shell_injection_via_argument_substitution`, `test_render_command_prompt_inserts_only_approved_output` (4) |

Total: **18 tests**, all passing. `py_compile` clean on both new Python files.

## Design decisions worth the lead's attention

1. **Identity comes from the path, deterministically.** A command file's
   repository-relative POSIX path becomes its id: `team/review.md` →
   `team/review`, `team/deep/ship.json` → `team/deep/ship`; the display title is
   `/team/review`. Backslashes are normalised, extensions are restricted to
   `.md`/`.json`, and id segments are validated. An optional explicit
   `CommandSource.command_id` models aliases/overrides while still passing
   segment validation (W5.1).
2. **Containment is lexical and fail-closed.** `assert_contained_command_path`
   refuses absolute, drive-qualified, UNC, empty, `.`, `..` and NUL-bearing
   segments before any separator normalisation; the root is an opaque anchor
   label. No filesystem lookup or symlink resolution is performed here, so the
   check cannot race or be confused by a symlink in the caller's tree (W5.1).
3. **One precedence key, no special cases at call sites.** Winners are chosen
   by `(custom > builtin, project > global, nearer > ancestor, source_path,
   format, content fingerprint)` — higher wins. String tie-breakers make the
   result independent of discovery order. Built-ins are ordinary descriptors
   with `source_kind = builtin` and an empty template, so a custom command can
   replace one without a second lookup path (W5.1).
4. **Hot reload is a pure content-addressed rebuild.** `CommandRegistry.fingerprint`
   is SHA-256 of canonical JSON of the resolved descriptors; `hot_reload`
   re-builds from newly supplied sources and reports `changed`, `added_ids`,
   `removed_ids` and `changed_ids`. Identical content is a no-op. A caller's
   file watcher supplies fresh `CommandSource` texts — this module never polls
   or reads files (W5.1).
5. **Frontmatter is small and typed.** Markdown accepts an optional `---`
   fence (a fence-less file is a valid prompt-only command) or JSON accepts an
   object with `template`/`body`/`prompt`. Unquoted YAML-ish flow collections,
   booleans and integers get native types, so `agent: [a, b]` or `model: 42`
   raise `CommandValidationError` with the offending `.field`; a malformed
   fence or JSON object raises `CommandParseError`. All failures derive from
   `CommandContractError` (W5.2).
6. **`subagent` has three states.** `true` forces a subagent, `false` forces
   the main agent, omission means inherit (`None`); the descriptor records
   `subagent_source` as `field`, `legacy` or `omitted`. `subtask` is the legacy
   alias of the same field; a conflicting explicit `subagent` + `subtask` pair
   raises instead of silently choosing one (W5.2).
7. **Substitution is one non-recursive pass.** `shlex` is used only to group
   quoted tokens (including explicit empty tokens) — it expands nothing.
   Placeholders are replaced with a single regex callback, so an argument
   containing `$2`, `$(id)`, backticks or `; rm -rf /` is inserted literally
   and never re-scanned or executed. The highest positional index used gets
   all remaining tokens joined by single spaces; missing tokens are empty;
   with no placeholder the raw arguments are appended after a blank line
   (W5.3).
8. **Shell markers are descriptors, not actions.** Only bang-backtick markers
   in the *template* become `ShellCommandDescriptor`s; argument text cannot
   create one. Each descriptor is content-id'd by position + command, carries
   `tier = 2`, `executed = False`, `output = None`, and always
   `approval_required = True`. `permission_gate_for()` describes the required
   Tier 2 gate with `show_resolved_command = True` and
   `runs_outside_agent_permission_flow = False` — the deliberate Keel
   difference from opencode (W5.4, C-3). `render_shell_output` inserts
   caller-supplied output only when `approved=True` is passed explicitly;
   otherwise it raises `ShellApprovalError`. `render_command_prompt` swaps
   descriptors for opaque sentinels before substitution and restores them in
   one pass, so neither arguments nor inserted output can be re-parsed as new
   shell markers.

## Test results

Command (from worktree root):

```
python -c "import sys,pytest; sys.path.insert(0,'keel/src'); raise SystemExit(pytest.main(['-q','keel/tests/test_command_contracts.py']))"
```

Result: `18 passed` (0.78 s). Python 3.11.9, pytest 9.0.2.
Neighbourhood check with the pre-existing slash-command tests:

```
python -c "import sys,pytest; sys.path.insert(0,'keel/src'); raise SystemExit(pytest.main(['-q','keel/tests/test_command_contracts.py','keel/tests/test_slash_commands.py']))"
```

Result: `32 passed` (1.94 s). No existing test file was modified.

## Exact integration seams needed by the lead

This module is deliberately not wired into the live runtime. To adopt it:

1. **`keel/commands.py` (W5.1, W5.2)** — replace the flat
   `root.glob("*.md")` discovery with a caller-side walker feeding
   `CommandSource(relative_path=<path relative to command root>, text=..., scope=...)`
   into `CommandRegistry.build`. Keep `custom_command_roots()` as the source
   of global/project roots; walk `**/*.md` and `**/*.json`. Map each returned
   `CommandDescriptor` onto the existing `Command` dataclass (`name`,
   `description`, `template`, `source`) or its successor.
2. **File watcher / settings (W5.1 hot reload)** — on command-file change,
   re-read only texts and call `hot_reload(current_registry, sources)`; apply
   the new registry only when `changed` is true. No watcher belongs in this
   module.
3. **Prompt execution path / CLI (W5.3)** — replace `commands.render_custom`
   with `render_command_prompt(descriptor, arguments)`; honour `agent`, `model`
   and `subagent` from the descriptor when the session loop builds a turn
   (subagent = main-agent force when `False`, inherit when omitted).
4. **Permission gate / Tier 2 (W5.4, C-3)** — when a `RenderedPrompt` has
   pending descriptors, show `descriptor.command` to the user, route the
   actual execution through the existing shell permission gate at Tier 2,
   then call `render_command_prompt(..., outputs={id: output},
   approvals={id: True})`. Never execute from this module and never insert
   output without the explicit approval flag. Keep this stricter behaviour:
   opencode's bang-backtick injection outside the permission flow is an
   intentional difference, not a target to copy.
5. **Persistence / provenance (all IDs)** — descriptors and
   `RegistryReload.to_dict()` payloads are JSON-serialisable and stable by
   content fingerprint, so they can be logged or stored verbatim without
   adding time-, path- or order-dependent fields.
