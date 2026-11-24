# Addendum 6 — D1.x plugin architecture (P0): implementation evidence

Branch: `agent/a6-d1` (worktree `.../worktree/addenda/a6-d1`)
Baseline: `4f64b8e`, read-only.
Source of requirements: `PLAN-INDEX.json` → `features[]`, owned IDs **D1.1,
D1.4, D1.5, D1.10, D1.12** (all `priority=P0`, `implementation_tier=local_module`,
`status=not_started`; milestones M2/M7/M10/M19/M19+M22).

This workstream is **additive**. No existing source file, test, CLI, config
loader or Electron code was edited. The canonical implementation lives in one
new module and is exercised by one new permanent contract-regression test file.
Integration into the live runtime is a separate lead decision (exact seams at
the end).

## Files owned

| File | Purpose |
| --- | --- |
| `keel/src/keel/plugin_contracts.py` | Canonical implementation of all five D1.x contracts. Stdlib only; pure config/data; no plugin imported, instantiated or executed; no import-time I/O. |
| `keel/tests/test_plugin_contracts.py` | 39 permanent tests: layer ordering, protected-core precedence, provenance, no secret leakage, descriptor completeness, typed descriptors and core package map. |
| `master-plan-v6-plugin-contracts-evidence.md` | This document. |

## Contracts implemented

| ID | Registry requirement | Primary symbols | Tests |
| --- | --- | --- | --- |
| D1.1 | Every part is a plugin — model adapter, tool registry, session log, approval broker, agent loop — each registerable from configuration; "no privileged core to patch". Tier 2 safety services are plugins that cannot be replaced or disabled by profiles/patches. | `PartKind`, `ServiceTier`, `PluginPart`, `PluginRegistry`, `core_parts`, `default_registry`, `PROTECTED_CORE_IDS`, 3 typed errors | `test_every_core_part_is_a_typed_plugin_descriptor_*`, `test_permission_and_safety_core_are_protected_*`, `test_same_registration_api_for_core_and_extensions`, `test_part_descriptor_validation_and_round_trip` (4) |
| D1.4 | Layered composition: bundles in order → profile patch → home patch → project patch → `--patch` overlays; replace whole row by id, insert new rows, `preset` edits inside a declaration's plugin list; deterministic merge; protected core cannot be overridden. | `Layer`, `LAYER_ORDER`, `ConfigRow`, `row`, `Bundle`, `Patch`, `PatchAction`, `PluginListOp`, `PatchDocument`, `Composition`, `ordered_layer_docs`, `compose`, `ProtectedCoreOverride`, `PatchError` | `test_layer_order_is_bundles_*`, `test_later_layers_win_on_config_*`, `test_composition_is_deterministic_*`, `test_protected_core_cannot_be_replaced_*`, `test_protected_core_cannot_be_disabled_*`, `test_protected_core_restated_identically_*`, `test_patch_replace_insert_disable_and_preset_*`, `test_preset_replace_operation_and_bad_patch_targets`, `test_composition_rows_and_config_are_not_aliases` (9) |
| D1.5 | `--dump-config`: print the exact plugin tree the machine will boot; any printed row can be replaced by a patch; provenance on every row; no secret values. | `dump_config`, `dump_config_json`, `dump_config_rows`, `redact_config`, `redact_value`, `assert_no_secrets`, `find_secret_patterns`, `REDACTED` | `test_dump_config_prints_exact_boot_tree_with_provenance`, `test_dump_rows_are_the_composition_with_redaction_and_layer_field`, `test_no_secret_values_in_dump_known_and_pattern_based`, `test_redaction_is_recursive_and_does_not_mutate_source`, `test_dump_config_json_matches_text_view_and_is_secret_free` (5) |
| D1.10 | Desktop shell: Electron ships the exact production runtime in signed resources, owns the UI, reserved `desktop` profile, private Electron-as-Node host with OS-assigned port and per-launch token, packaged assets then boot injections then plugins, Node IPC channels, shared data / separate packages+activation+lockfiles. Descriptor only — no packaging. | `DesktopShellDescriptor`, `desktop_shell_descriptor`, `assert_descriptor_complete`, `BOOT_SEQUENCE`, `IPC_CHANNELS`, `IpcChannel`, `RESERVED_DESKTOP_PROFILE`, `DescriptorError` | `test_canonical_desktop_descriptor_is_complete`, `test_boot_sequence_loads_assets_before_activating_plugins`, `test_incomplete_descriptors_fail_closed` (14 parametrized cases), `test_descriptor_is_data_only_no_packaging_side_effects` (17 cases) |
| D1.12 | Core package map — session log, system-prompt assembly, tool registry + guarded pipeline, agent interface + live registry, agent loop driver, LLM vocabulary + adapter seam — each exposing one service key on the context. | `CoreService`, `CORE_SERVICE_KEYS`, `CORE_PACKAGE_MAP`, `core_package_map`, `core_service_keys`, `assert_core_map_complete` | `test_core_map_has_exactly_six_context_service_keys`, `test_every_core_service_has_responsibility_and_part_reference`, `test_tool_registry_service_is_marked_guarded`, `test_core_map_copy_cannot_mutate_canonical_and_validation_fails_closed` (4) |

Total: **39 tests, all passing** (3 consecutive runs: 0.82 s / 0.78 s / 0.80 s).
`py_compile` clean on both new Python files. No existing test was modified.

## Design decisions worth the lead's attention

1. **One registration API, no privileged patch path (D1.1).** `core_parts()`
   returns nine `PluginPart` descriptors and `default_registry()` registers them
   through `PluginRegistry.register()` — exactly the call an out-of-tree plugin
   uses. `implementation` is an inert `module:qualname` string validated by a
   regex; this module never imports or calls it. The four central services the
   registry calls out (model adapter, tool registry, session log, agent loop)
   are ordinary replaceable parts. Permission core, safety core and the
   approval broker are the documented Tier 2 exception: still plugins, but
   `protected=True`, `replaceable=False`, so profiles and patches cannot remove
   them (D1.1 detail).
2. **Composition order is a function, not a convention (D1.4).**
   `ordered_layer_docs()` is the single place that fixes the canonical order:
   every bundle in list order, then profile, home, project and each `--patch`
   overlay in CLI order — independent of the order in which a caller supplies
   them. `compose()` replays that list once, so the merge is deterministic and
   `Composition.fingerprint` (SHA-256 of canonical JSON) is stable. Rows keep
   the slot of their first appearance; later layers replace config and
   provenance, never identity. A protected row may be *restated identically*
   by a later layer (no-op, first provenance kept); any real change raises
   `ProtectedCoreOverride`. `REPLACE` replaces the whole config (not a deep
   merge); `INSERT`, `DISABLE` and `PRESET` (`add`/`remove`/`replace` on a
   preset row's `plugins` list) cover the registry's patch semantics.
3. **The dump is the boot tree, and it is safe to print (D1.5).**
   `dump_config()` walks `Composition.rows` in order — the same objects the
   boot path will consume — so row count, ids and order always match the
   composition, and each row carries `[layer=... source=...]`. `config` is
   passed through `redact_config()`: keys matching secret/auth patterns and
   values matching credential patterns (`sk-`, `ghp_*`, `xox*`, `AKIA`,
   `Bearer …`, PEM private-key headers) become `<redacted>`, recursively.
   `assert_no_secrets()` runs on the final rendered text, and the JSON variant
   ("What is running" UI) is checked the same way. Source dicts are copied,
   never mutated.
4. **The desktop contract is fail-closed and inert (D1.10).**
   `desktop_shell_descriptor()` returns one validated value. `assert_descriptor_complete()`
   checks all eleven obligations, including `signed_resources` +
   `repackaging_allowed=False` (exact production runtime), `ui_owner=
   electron_shell`, `os_assigned` port 0 + per-launch token env, the exact
   four-step boot order (assets → host → injections → same-document plugin
   activation), all four IPC channels, the fatal-error screen, and shared data
   with separate packages/activation/lockfiles. `packaging='descriptor_only'`
   and there is no subprocess, signing or file-write code anywhere in the
   module. Every incomplete variant raises `DescriptorError`.
5. **The service map is typed and self-checking (D1.12).** Exactly six keys,
   each with a non-empty responsibility, a package descriptor, one context key
   and a resolvable `part_id` from D1.1. `assert_core_map_complete(registry)`
   also verifies the `tools` service carries the guarded pipeline. Returned
   maps are copies so callers cannot drift the canonical contract at runtime.

## Test results

Command (from worktree root):

```
python -c "import sys,pytest; sys.path.insert(0,'keel/src'); raise SystemExit(pytest.main(['-q','keel/tests/test_plugin_contracts.py']))"
```

Result: `39 passed` (3 consecutive runs: 0.82 s / 0.78 s / 0.80 s).
Python 3.11 / pytest 9.x. No existing test file was modified.

## Exact integration seams needed by the lead

This module is deliberately not wired into the live runtime. To adopt it:

1. **Plugin host / scope tree (D1.1; V1, W1.1)** — use `default_registry()` as
   the registration manifest for the existing scope tree: each
   `PluginPart.implementation` string is resolved and loaded by the host (this
   module never resolves it). Keep `ProtectedCoreOverride` in the load path so
   a profile or patch cannot unregister `permission_core`, `safety_core` or
   `approval_broker`; scope disposers from V1/D1.2 remain the unload mechanism.
2. **Config loader and CLI (D1.4; D1.3)** — replace ad-hoc dict merging in the
   config loader with `compose()`: emit one `Bundle` per shipped bundle in
   declared order, wrap the selected profile, `~/.keel` home and project
   overlays in `PatchDocument`s, and wrap each `--patch file.yml` as a final
   `PatchDocument(layer=PATCH)`. Give every config row the stable `id` the
   composer expects; use `PatchAction.PRESET` for edits inside a declaration's
   plugin list.
3. **`--dump-config` and the UI (D1.5; X6.8)** — add the CLI flag to render
   `dump_config(composition)` (or `dump_config_json()` for the web "What is
   running" view). `dump_config_rows()` already supplies `source_layer` and
   `source` for the X6.8 layered config viewer: show the winning layer and let
   the viewer generate a `PatchAction.REPLACE` row targeted at that id.
4. **Electron main / packaged assets (D1.10)** — hand
   `desktop_shell_descriptor().to_dict()` to the shell bootstrap. The main
   process must actually sign/package the runtime and resources (out of scope
   here), bind loopback on port 0 with `KEEL_DESKTOP_TOKEN`, start the private
   Electron-as-Node host, show the splash from `boot_assets`, wait for the
   `boot-injections` IPC message before activating plugins in the same
   document, and surface `fatal-error` as the structured screen. Keep desktop
   plugin packages/activation/lockfiles under a separate directory while
   sharing the product data dir with the CLI; reserve the `desktop` profile so
   no other profile can claim it.
5. **Context builder (D1.12)** — build the runtime context from
   `core_package_map()`: register exactly one service per key under that key,
   resolving each `part_id` through the plugin registry from seam 1. The
   `tools` service entry must wrap its registry in the guarded pipeline that
   consults the protected approval broker.

No change to `keel/tool_contracts.py`, `keel/session_contracts.py`,
`keel/transcript_contracts.py` or `keel/capability_registry.py` is required:
those modules govern tool/session/transcript payloads and capability dispatch;
this one governs plugin part descriptors, layer composition, boot-tree
rendering, the desktop shell contract and the six core service keys.
