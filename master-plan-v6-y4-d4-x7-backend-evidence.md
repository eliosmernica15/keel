# Y4 / D4 / X7 backend completion — implementation evidence

**Branch:** `agent/b3-y4` · **Baseline:** `73b2a90` (clean tree at start)
**Worktree:** `C:\Users\Admin\.local\share\opencode\worktree\backend\b3-y4`

## Scope confirmed from the registry

A programmatic read of `PLAN-INDEX.json` found **37** rows with an ID prefix of
`Y4.`, `D4.` or `X7.`:

* **31 `not_started`** — the implementation scope of this assignment:
  * `Y4.*` (11): Y4.1, Y4.2, Y4.4, Y4.5, Y4.6, Y4.7, Y4.8, Y4.10, Y4.11, Y4.12, Y4.14
  * `D4.*` (10): D4.1, D4.3, D4.4, D4.5, D4.6, D4.8, D4.9, D4.10, D4.12, D4.13
  * `X7.*` (10): X7.1 … X7.10
* **6 `verified` P0 rows already implemented** — verified/documented here, not
  re-implemented: Y4.3, Y4.9, Y4.13 (in `keel.identity_contracts`) and D4.2,
  D4.7, D4.11 (in `keel.composition_contracts`).

`PLAN-INDEX.json`, all existing source modules, and all other files were left
untouched. No row status was changed; no push, release or visibility change was
performed.

## Files owned (only these three were added)

* NEW `keel/src/keel/y4_d4_x7_backend.py`
* NEW `keel/tests/test_y4_d4_x7_backend.py`
* NEW `master-plan-v6-y4-d4-x7-backend-evidence.md` (this file)

## What "backend behavior" means here

The module is stdlib-only (`dataclasses`, `enum`, `pathlib`, `hashlib`, `json`,
`io`, `gzip`, `tarfile`, `re`, `os`, `typing`) and deterministic. It exposes
pure contracts, stores, planners and verifiers. It never renders UI, opens a
socket, starts a process or reads the host clock/chance on import. Callers own
all ticks, file bodies, credentials and environment maps. Things that genuinely
require an external runner (tunnels, installers, app stores, CI, AV vendors,
OS protocol registration, desktop drivers) are represented as explicit,
validated *plans/descriptors* with conservative gates — never as fake success.
Fencing categories: no secret values are logged or echoed; path-containment is
enforced for vault/import/disk operations; dry-run is the default for import and
cleaning.

## Requirement → implementation map (all 31 not_started IDs)

| ID | Registry requirement (short) | Backend surface in `keel.y4_d4_x7_backend` |
| --- | --- | --- |
| Y4.1 | `/mcp` revives dormant MCP servers instantly; ~5 min configurable re-probe | `McpServerReviver` (`reload()` = instant, `probe_due()`/`due_servers()` with `DEFAULT_PROBE_INTERVAL_S = 300`), `ServerPhase`, `ReviveResult` |
| Y4.2 | QR/deep-link chat onboarding; always a manual fallback | `build_onboarding_payload`, `PairingPayload` (qr_text == deep_link), `has_manual_fallback`, `PairingChannel` |
| Y4.4 | Named vault map, fields = env vars, token in separate env file, shipped disabled, `op`/`pass`/`bw` non-interactive gate | `SecretProviderMap` (disabled until enabled), `ProviderBinding`, `is_non_interactive`, `enable()`, `SecretProvider` |
| Y4.5 | Supervised webhook bridge, user-provided tunnel, wakes when keyed | `SupervisedBridge` (`provision_plan`, `start`, `wake_if_keyed`, `deliver`), `BridgePhase` |
| Y4.6 | Local traces + internal `traces` MCP/tool query | `TraceStore` (`record`, `query`, `what_did_you_do`, `mcp_tool_descriptor`), `TraceEvent` |
| Y4.7 | 11 key-less desktop-control tools on VM auth | `KEYLESS_DESKTOP_TOOLS`, `desktop_tool_manifest`, `validate_desktop_tools` |
| Y4.8 | Agent-readable/writable plain-Markdown Obsidian vault | `ObsidianVault` (`create_note`, `read_note`, `list_notes`, `note_path` with containment), `editor_command` (argv, no shell) |
| Y4.10 | Skill library: 21 setup runbooks mapped to connectors | `SKILL_RUNBOOKS`, `list_runbooks`, `resolve_runbook`, `validate_skill_library` |
| Y4.11 | Provider switch in two config.yaml lines + reference examples | `two_line_switch`, `config_reference_examples`, `is_two_line_switch` |
| Y4.12 | Reproducible tarball + per-target size budget | `deterministic_tarball` (sorted names, zeroed tar metadata, mtime-0 gzip), `check_artifact_budget`, `ARTIFACT_SIZE_BUDGETS` |
| Y4.14 | One preset: 16 plugins + 13 free MCP servers (C1.9) | `PRESET_PLUGINS`, `FREE_MCP_SERVERS`, `preset_bundle`, `validate_preset` |
| D4.1 | Provider form hot-applies; inline test result; no restart | `ProviderRegistry` (`configure`/`resolve`/`snapshot` with `restart_required=False`), `RouteTest` |
| D4.3 | Composer locked until explicit workspace selection; empty state; Cowork chat optional | `WorkspaceGate`, `WorkspaceState`, `empty_state`, `can_compose`, `chat_allowed` |
| D4.4 | In-page vs native picker; overlay pin for tests; headless support | `PickerMode`, `PickerConfig`, `resolve_picker_mode`, `list_directories` |
| D4.5 | Extensible `ConversationNodeDefinition` + keyed renderer registry | `ConversationNodeDefinition`, `NodeRendererRegistry` (`register`, `render`) |
| D4.6 | Plugin-contributed schema-driven settings cards | `SettingsCard`, `SettingField`, `SettingsCardRegistry` (`register_manifest`, `render_form`) |
| D4.8 | Locale-owned copy; `verify_ui_copy` gate; sentence-case titles | `t`, `verify_ui_copy`, `is_sentence_case`, `CopyIssue` |
| D4.9 | Consistent bundled icon set; new glyphs need designer approval | `APPROVED_ICONS`, `check_icon`, `verify_bundled_icons` |
| D4.10 | Reusable design-review skill; `UI-UX-GUIDE.md` loaded before UI change | `DesignGuideSkill` (`load`, `load_reference`, `gate`, `is_ui_change`), `DESIGN_PRINCIPLES`, `DESIGN_REFERENCES` |
| D4.12 | Packaged assets paint first; plugins activate after readiness | `StartupPhase`, `STARTUP_PHASES`, `desktop_startup_plan`, `is_valid_startup_order` |
| D4.13 | Web fixed port, desktop OS-assigned, profile override, clear conflicts | `WEB_DEFAULT_PORT = 8739`, `PortMode`, `select_port`, `PortDecision` |
| X7.1 | ARM64 Win/Linux; macOS universal or split, native deps verified | `PlatformTarget`, `BUILD_TARGETS`, `verify_target_matrix`, `verify_native_deps` |
| X7.2 | Windows per-user vs per-machine install; no admin for per-user | `InstallScope`, `windows_install_plan` |
| X7.3 | Uninstall modes; list deletions first | `UninstallMode`, `uninstall_plan` (dry-run, confirmation) |
| X7.4 | File associations + `keel://` protocol with clean removal | `FILE_ASSOCIATIONS`, `URL_PROTOCOL`, `association_registration_plan`, `association_removal_plan`, `verify_clean_removal` |
| X7.5 | Wayland/X11, tray fallback, AppImage integration, sandbox guidance | `detect_linux_session`, `linux_tray_plan`, `appimage_desktop_entry`, `sandbox_flags` |
| X7.6 | AV false-positive playbook, free vendor channels, checksums | `ANTIVIRUS_PLAYBOOK`, `AV_SUBMISSION_CHANNELS`, `checksum_manifest`, `antivirus_playbook` |
| X7.7 | Installer locales from the same string catalogs | `INSTALLER_LOCALES`, `installer_text`, `installer_catalog_issues` |
| X7.8 | In-app download-integrity helper | `verify_download`, `parse_checksum_line`, `DownloadVerification` |
| X7.9 | First-run import wizard, documented formats, dry-run first | `IMPORT_FORMATS`, `plan_import`, `execute_import` (dry-run default, containment) |
| X7.10 | Disk manager: models/caches/sessions/trash, sizes, safe-clean, caps | `scan_disk_usage`, `safe_clean_plan`, `DISK_CATEGORIES`, `DEFAULT_CATEGORY_CAPS` |

Coverage is machine-checkable: `FEATURE_BEHAVIORS` maps every ID to the
symbols that implement it, `IMPLEMENTED_FEATURE_IDS` has exactly 31 entries,
and `verify_coverage()` returns `()` (no issues).

## Verification of the six prior P0 rows (verify/document, no changes)

Run from the worktree root with the required `sys.path` insert:

```
python -c "import sys,unittest; sys.path.insert(0,'keel/src'); \
suite=unittest.defaultTestLoader.discover('keel/tests',pattern='test_identity_contracts.py'); \
raise SystemExit(0 if unittest.TextTestRunner().run(suite).wasSuccessful() else 1)"
```

Result: **69 tests passed** — Y4.3 (first-boot sign-in test-fire), Y4.9
(persona/SOUL + routing), Y4.13 (version badge + zero-secrets scan).

```
python -c "import sys,unittest; sys.path.insert(0,'keel/src'); \
suite=unittest.defaultTestLoader.discover('keel/tests',pattern='test_composition_contracts.py'); \
raise SystemExit(0 if unittest.TextTestRunner().run(suite).wasSuccessful() else 1)"
```

Result: **51 tests passed** — D4.2 (OpenAI-compatible endpoint path), D4.7
(pure tool presenters), D4.11 (plugin manager contracts). These rows remain
`verified` at baseline; their modules and tests were not edited.

## Verification of the 31 new features

Stdlib-only runner (the required invocation):

```
python -c "import sys,unittest; sys.path.insert(0,'keel/src'); \
suite=unittest.defaultTestLoader.discover('keel/tests',pattern='test_y4_d4_x7_backend.py'); \
raise SystemExit(0 if unittest.TextTestRunner().run(suite).wasSuccessful() else 1)"
```

Result: **43 tests passed, 0 failed** (`Y4.1 … X7.10`, one dedicated test class
per feature plus coverage tests; `verify_coverage()` asserted empty).

Pytest cross-check:

```
python -c "import sys,pytest; sys.path.insert(0,'keel/src'); \
raise SystemExit(pytest.main(['-q','keel/tests/test_y4_d4_x7_backend.py']))"
```

Result: **43 passed in 4.73 s**. `python -m py_compile` on both new Python files
succeeded.

## Honest limitations

* No frontend/UI/visual code was written. D4 features are host-side contracts
  (gates, registries, plans) that a renderer would consume; the renderer itself
  is out of scope for this backend assignment.
* X7 distribution features are planners/validators and string/size helpers;
  producing signed OS installers, registering real protocol handlers, uploading
  to stores or submitting to AV vendors needs external tooling and owner
  decisions and is explicitly not simulated as "done".
* Y4.5/Y4.6 model tunnels/traces locally: no real tunnel is provisioned and no
  host telemetry is collected — the caller supplies events and tunnel URLs.
* The UI-copy gate is a deterministic heuristic over supplied source strings,
  not a JavaScript parser; it flags unwrapped string literals and title-case
  plugin titles for a renderer/manifest author to fix.
* No row status in `PLAN-INDEX.json` was changed; integration must review the
  diff and mark the 31 IDs verified in its own registry step.
