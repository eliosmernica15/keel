# Composition contracts — implementation evidence (D4.x P0 assignment)

**Branch:** `agent/a8-d4` · **Baseline:** `4e0b804`
**Worktree:** `C:\Users\Admin\.local\share\opencode\worktree\addenda\a8-d4`

## Scope and registry note

The assignment was to read the full text of every `not_started` **P0** `D4.*`
row in `PLAN-INDEX.json` and implement the pure composition/layering contract
surface in three new files. Reading the registry at the assigned baseline found
exactly three such rows. Their full text is reproduced here for traceability:

| ID | Full registry feature text | Detail | Milestones | Status |
| --- | --- | --- | --- | --- |
| D4.2 | Custom OpenAI-compatible endpoints documented as a first-class path. | Provider type "OpenAI-compatible" (local servers, LAN). | M2 | `not_started` / P0 |
| D4.7 | Tool UI presentation designed up front: host presenters are pure; web cards derive from raw events and persisted result metadata. | Each tool ships a presenter (summary, icon, expanded view) as a pure function over events. | M5, M19 | `not_started` / P0 |
| D4.11 | Plugin Manager UI in the base bundle for Web and agents. | Extensions page (Y1.31) also usable by agents with approval. | M10, M19 | `not_started` / P0 |

All three live in section "5. Web UI, Desktop, chat nodes and UX" of
`Keel_Master_Plan_v6.md` and describe product UI/documentation work; D4.11
references the bundled Extensions page (Y1.31). The explicit deliverable
specification — a stdlib-only, pure **typed composition/layering descriptors,
deterministic merge, protected-core precedence, path containment, no secret
leakage and fail-closed validation** surface — is unambiguous, so this change
implements that specification as the host-side contract layer those UIs would
consume. `PLAN-INDEX.json` and all other existing files were **not** edited; no
row status was changed here, and this evidence does not claim the Web/Desktop
UI itself was shipped or verified end-to-end.

## Files owned (only these were added)

* NEW `keel/src/keel/composition_contracts.py`
* NEW `keel/tests/test_composition_contracts.py`
* NEW `master-plan-v6-composition-evidence.md` (this file)

## Required behaviour → implementation map

| Requirement | Contract surface in `keel.composition_contracts` |
| --- | --- |
| Typed composition/layering descriptors | `LayerOrigin` (`CORE`/`BUNDLE`/`PLUGIN`/`AGENT`/`USER`/`UNKNOWN`), `LayerDescriptor`, `make_layer`, `Composition`, `ProviderDescriptor`, `PresenterDescriptor`, `PluginDescriptor`, `SecretRef` (all frozen dataclasses) |
| Deterministic merge (order independent) | `_winners`/`_stable_key`, `merge_providers`, `merge_presenters`, `merge_plugins`, `compose_layers`; tuples sorted by key and tied by canonical JSON |
| Protected-core precedence | `PROTECTED_ORIGINS = {CORE, BUNDLE}`, `_merge_rank` (group 0 core/bundle always beats group 1 plugin/agent/user; within group 1 a higher layer such as a profile patch wins), `Composition.from_dict` re-merges on load, `set_plugin_enabled` refuses to disable protected plugins |
| Path containment | `safe_join`, `is_contained`, `_normalize_contained`, `_split_segments`: purely lexical (no I/O, no symlink resolution); rejects `..`, absolute/drive/UNC paths, encoded `%2e%2e`/`%2f`/`%5c` and control/NUL bytes; plugin resource paths must stay under `plugins/` |
| No secret leakage | `SecretRef` (indirection only: `env:`/`keyring:`/`secret:`/`file:`), `parse_secret_ref`, `looks_like_secret`, `redact`; literal keys rejected by `make_provider`/`make_secret_ref`; `ContractValidationError` redacts every message; `to_public_dict()`/`to_dict()` never carry a value; presenter secret fields are rejected and secret-looking values in events are redacted |
| Fail-closed validation | `validate_provider`, `validate_presenter`, `validate_plugin`, `validate_composition`, `ContractValidationError`; unknown kinds/origins/capabilities map to `UNKNOWN` or are rejected, disabled and unknown layers contribute nothing, unknown tool/agent/plugin lookups return `None` or deny |
| D4.2 — OpenAI-compatible as first class | `ProviderKind.OPENAI_COMPATIBLE` (+ aliases `OpenAI-compatible`, `compatible`, `ollama`, `llama.cpp`), `ProviderDescriptor.is_openai_compatible`, `endpoint_scope` (`local`/`lan`/`remote`) for local servers and LAN, URL validation (http(s), host, no embedded credentials, no secret in query) |
| D4.7 — pure presenters | `PresenterDescriptor` + `present(spec, event, metadata)` builds summary/icon/expanded view from raw events and persisted metadata only; `render_tool_card` picks the merged winner per tool and falls back to a generic card; `Presentation`/`to_dict()` are immutable results |
| D4.11 — bundled Plugin Manager / agent approval | `make_plugin(..., origin=BUNDLE)` marks the bundled manager protected; `can_activate_plugin(plugin, approved=...)` gates extensions (unknown origin/disabled/approval missing all deny); `with_plugin_enabled` and `set_plugin_enabled` enforce protection |
| No network/subprocess/host state | stdlib-only imports (`ipaddress`, `json`, `re`, `dataclasses`, `enum`, `typing`, `urllib.parse`, `__future__`); no file, process, clock, chance or transport calls |

## Verification

Both commands were run from the worktree root with the required `sys.path`
insert.

```
python -c "import sys,unittest; sys.path.insert(0,'keel/src'); suite=unittest.defaultTestLoader.discover('keel/tests',pattern='test_composition_contracts.py'); raise SystemExit(0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1)"
```

Result: **51 tests passed in 0.037 s** (stdlib-only runner).

```
python -c "import sys,pytest; sys.path.insert(0,'keel/src'); raise SystemExit(pytest.main(['-q','keel/tests/test_composition_contracts.py']))"
```

Result: **51 passed, 44 subtests passed in 0.85 s**.

## Adversarial coverage (all green)

* **Secret leakage** — literal `sk-`/`ghp_`/`xoxb-`/`AKIA` keys and
  `api_key=...` assignments are detected; a literal key passed as `secret_ref`
  or placed in provider metadata is rejected, and the error text contains
  `[REDACTED]` instead of the key; a serialized `secret_ref` with an injected
  `value` field is rebuilt without that field; `to_public_dict()` of a provider
  and of a whole composition contains no key material.
* **Path traversal** — `../` escapes, multi-segment pops above the root,
  absolute paths, Windows drive letters (`C:\...`), UNC (`\\server\share`),
  encoded dot/slash/backslash (`%2e%2e`, `%2f`, `%5c`) and NUL/control bytes are
  all refused by `safe_join`/`is_contained`; plugin resource paths outside
  `plugins/` are rejected at construction.
* **Protected-core precedence** — a plugin provider/presenter for a key owned
  by core or bundle never wins, even when layers are supplied in reverse order
  or a forged plugin-origin row is appended to a serialized composition;
  `set_plugin_enabled` refuses to disable the bundled Plugin Manager.
* **Determinism** — equal merges are produced regardless of layer/contribution
  order; ties are broken by canonical JSON of the public descriptor; results
  are frozen tuples, and `Composition.to_dict()` is byte-for-byte equal across
  orderings.
* **Fail-closed gates** — extension activation denies missing approval,
  disabled plugins, unknown origins and unknown capabilities; disabled and
  unknown-origin layers contribute nothing; empty identifiers, bad URLs,
  secret-bearing URLs, bad icons/field names and unknown provider kinds are
  rejected; missing lookups return `None`.
* **Pure presenters** — `present` is deterministic and reads only event/metadata
  mappings (event wins over stale metadata, including falsy values like
  `exit_code=0`); secret-named fields are rejected at construction and secret
  values in events are redacted; unknown tools get a generic card rather than
  host code being imported.
* **Purity** — a test parses the module with `ast` and asserts the only imports
  are the permitted stdlib set and there are no `open`/`system`/`popen`/`spawn`
  calls.

## TDD evidence

`test_composition_contracts.py` was written first and run before the module
existed; collection failed with
`ModuleNotFoundError: No module named 'keel.composition_contracts'`. After the
module was added the suite exposed four real defects, each diagnosed and fixed
in the implementation (not by weakening the assertions):

1. `redact(0)` returned an empty string because of a `value or ""` idiom —
   falsy but valid event values (`exit_code=0`) vanished from expanded cards;
   fixed to only map `None` to empty text.
2. Merge ranking treated protected and ordinary layers with the same numeric
   order, so a plugin beat a user/profile patch — fixed with the two-group
   `_merge_rank` (protected core/bundle first; higher ordinary layer wins).
3. Plugin resource paths were prefixed twice (`plugins/plugins/ext/ui.js`) —
   fixed with `_normalize_contained`, which canonicalizes an already-contained
   path without re-anchoring it.
4. The round-trip tamper test originally corrupted every row, making the
   expected core value unrecoverable; corrected to append a forged
   plugin-origin override while leaving the protected core row intact, so the
   test actually probes re-applied precedence.

The suite then reached 51/51 green (also under pytest).

## Design notes

* **Composition is a pure, keyed fold.** Each layer contributes typed
  descriptors; `_winners` reduces them per `(kind, key)` using a rank tuple and
  a canonical-JSON tie-break. Nothing depends on input order, host state or
  wall clock, so the result is reproducible across processes and platforms.
* **Protection is a property of origin, not of insertion order.** Core and
  bundled rows (including the bundled Plugin Manager) are group 0 and cannot be
  displaced by plugin/agent/user rows; ordinary layers may override each other
  in increasing authority. `from_dict` deliberately discards the incoming
  resolution and re-merges, so a tampered payload cannot smuggle an override.
* **Secrets are references only.** A descriptor stores `SecretRef(source,
  name, required)`, never a value. Detection is defence in depth: literal
  keys are rejected at the boundary, scrubbed from errors, skipped as presenter
  fields and redacted if an event still carries one.
* **Path safety is lexical and fail-closed.** Both separator styles and encoded
  forms are considered; no filesystem lookup or symlink resolution is
  performed, so containment is deterministic and safe over untrusted manifests.
* **Presenter purity is structural.** `present` takes mappings and returns a
  frozen `Presentation`; the Web card path (`render_tool_card`) derives from
  raw events plus persisted metadata and falls back locally instead of
  importing host code into the renderer.

## Integration seams for the lead (not made here — file ownership)

1. **Settings → Models (D4.1/D4.2)** — build provider rows with
   `make_provider(kind="OpenAI-compatible", base_url=..., secret_ref="env:...")`;
   show `endpoint_scope` and the inline test result; never place a key value in
   a descriptor or log (`to_public_dict()` is safe to emit).
2. **Web tool cards (D4.7 / E2.5)** — register one `PresenterDescriptor` per
   tool, merge them with `compose_layers`, and call `render_tool_card` on raw
   transcript events plus persisted result metadata; unknown tools fall back
   to the generic row.
3. **Plugin Manager / Extensions page (D4.11 / Y1.31)** — model the bundled
   manager with `origin=BUNDLE`; list extension rows from `composition.plugins`;
   call `can_activate_plugin(plugin, approved=...)` before an agent-driven
   enable/install, and use `set_plugin_enabled` so protected rows cannot be
   disabled. Plugin manifests should declare `capabilities` and contained
   `resource_paths`.
4. **Layered config (D1.3/D1.4)** — feed bundles/profile/home/patch overlays as
   `LayerDescriptor`s with the matching `LayerOrigin`; `compose_layers` gives
   the deterministic, protected-core-first resolution the loader needs.
