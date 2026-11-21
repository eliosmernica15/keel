# Implementation progress — post-recovery batches

Baseline: local HEAD `46f5f27` (M2, unpushed), `origin/main` `79200c3`, M1/M2 closed. Master Plan v5 remains incomplete; only explicitly available v5 requirements are used.

## Batch 1 — Runtime tool and MCP correctness

**v5 requirement:** §6 design rules for MCP client/server behavior, typed tool results and reliable filesystem tools; §11 MCP isolation and tool-path controls. No new milestone or acceptance criteria were invented.

**Implemented:**
- `src/keel/session.py`: imported `HttpMcpServer` so `isinstance()` checks for HTTP MCP clients no longer raise `NameError`. The broad `except Exception` had silently discarded all MCP resource/prompt context.
- `src/keel/mcp.py` + `src/keel/session.py`: stdio servers now retain their `initialize` capabilities, and resource/prompt discovery is attempted only when the server advertises those capabilities. This prevents unanswered discovery requests from consuming later tool responses on servers that support tools only.
- `src/keel/runner.py`: `RealTools._list_dir` now defines `fnmatch` and its ignore-pattern set locally and applies the same ignore rules in recursive and non-recursive listings.
- `tests/test_runtime_defects.py`: new regression tests for both non-recursive/recursive `list_dir` behavior and the imported MCP type.
- `tests/test_e2e_milestone_6b.py`: real Session+MCP integration test now asserts that resource and prompt content from a stdio MCP server reaches the first model turn.

**Verification:** `python -m pytest tests/test_runtime_defects.py tests/test_e2e_milestone_6b.py -q -s` → `4 passed`; `python -m pytest tests/test_runtime_defects.py tests/test_e2e_milestone_6b.py tests/test_mcp.py tests/test_v2_mcp_usage_images.py tests/test_tool_registry.py -q` → `36 passed` (2026-11-20). This includes a real stdio MCP server and the real Session/runtime, not a mock of the fixed code path.

**Remaining from defect register:** version mismatch, M2 API/UI integration, secret storage, hook coverage, artifact allowlist metadata, and distribution/signing gaps remain unchanged and unfixed.

## Batch 2 — Release consistency

**v5 requirement:** §0.4 (versioned releases, manifests, integrity) and §11 source-protection controls. No new milestone content was invented.

**Implemented:**
- `src/keel/__init__.py` version corrected to `0.1.1`.
- `scripts/check_version_sync.py` and `src/keel/release/common.py` now include the Python package version in version validation, preventing future silent drift.
- `site/download.json`: removed the internal `__hosting__` metadata key.
- `src/keel/release/artifacts.py`: `scan_tree()` now inspects JSON content for internal metadata keys (`FORBIDDEN_JSON_KEYS`) in addition to path patterns.
- `tests/test_version_sync.py` and additions to `tests/test_release_controls.py` cover both fixes.

**Verification:** `python scripts/check_version_sync.py` → `OK - all sources agree on version 0.1.1`; `python -m pytest tests/test_version_sync.py tests/test_release_controls.py tests/test_website_download_only.py -q` → `26 passed`. Windows packaging verification is running separately.

**Remaining from defect register:** secret storage, hook coverage, distribution/signing gaps, and the known hook/version-adjacent items remain for later batches.

## Batch 3 — M2 provider catalog reaches the real bridge/UI

**v5 requirement:** §7.1 M2 — JSONC + schema, `provider/model` naming, bundled offline provider catalog. No missing milestone content was invented.

**Implemented:**
- `src/keel/webapp.py`: added authenticated bridge endpoints:
  - `GET /api/model-catalog` (catalog metadata and provider summaries),
  - `GET /api/model-catalog/<provider>` (offline model identifiers),
  - `GET /api/settings/schema` (bundled settings schema),
  - `GET /api/models/resolve?ref=provider/model` (resolver result or clear 400).
- `site/ui/app.js`: `fetchCatalog()` now queries the local Keel bridge first and falls back to the provider's live catalog only for the public mirror.
- `tests/test_m2_api_integration.py`: real `webapp.make_server()` tests for all endpoints, auth, catalog-only rejection, and UI source integration.
- `node --check site/ui/app.js` passes.

**Verification:** `python -m pytest tests/test_m2_api_integration.py tests/test_m2_provider_config.py tests/test_webapp.py -q` → `38 passed`.

**Remaining from defect register:** secret storage, hook coverage, distribution/signing gaps.

## Batch 4 — Encrypted provider secret storage

**v5 requirement:** §8 free path (`keyring` master key, AES-256-GCM via `cryptography`, passphrase fallback) and §11 control 5 (secret storage and redaction). No new milestone content was invented.

**Implemented:**
- `src/keel/secret_store.py`: AES-256-GCM encryption/decryption with 12-byte random nonce; master key from OS keyring when available, `KEEL_MASTER_PASSPHRASE` or a local 0600 key file otherwise; errors never include secret material.
- `src/keel/settings_store.py`: saved provider keys are encrypted with `enc: aes256gcm-v1`; legacy plaintext keys remain readable and are migrated on the next save; env application and public projections use decrypted/material-free values only.
- `pyproject.toml`: added `cryptography>=42.0` and `keyring>=24.0` (both named by v5).
- `tests/test_secret_storage.py`: encryption-at-rest, legacy migration, public-view redaction, and env application tests.
- `docs/proprietary/THIRD_PARTY_NOTICES.draft.md`: added dependency notices.

**Verification:** `python -m pytest tests/test_secret_storage.py tests/test_fleet_credentials.py tests/test_settings.py tests/test_m2_provider_config.py -q` → `49 passed`.

**Remaining from defect register:** hook coverage, distribution/signing gaps.

## Batch 5 — Hook lifecycle integration

**v5 requirement:** §6 architecture (hooks in the Python daemon) and §11 control 9 (hooks/plugins cannot reach Tier 2). No M3 criteria were invented; only events with existing execution paths were wired.

**Implemented:**
- `src/keel/session.py`: wired SessionStart, UserPromptSubmit, PermissionRequest, PermissionDenied, PostToolUseFailure, PostToolBatch, PreCompact, PostCompact, Stop, StopFailure, and SessionEnd in addition to the existing PreToolUse/PostToolUse.
- Terminal hook firing is centralized so cancellation, provider errors, max-turn errors, and successful completion all emit Stop/StopFailure and SessionEnd exactly once.
- `src/keel/hooks.py`: docstring updated to reflect wired events.
- `tests/test_hooks.py`: ordering, failure, cancellation, and hook-failure-tolerance tests.
- `tests/test_compaction.py`: PreCompact/PostCompact boundary ordering test.

**Verification:** `python -m pytest tests/test_hooks.py tests/test_compaction.py tests/test_vertical_slice.py -q` → `33 passed`.

**Remaining from defect register:** distribution/signing gaps (Ed25519, updater, rollback, binaries-only endpoint); 20 declared hook events still have no runtime surface in this slice and are intentionally left inert rather than fabricated.

## Batch 6 — Locked platform targets

**v5 requirement:** §0.4 platform list — Windows installer, macOS Apple Silicon and Intel, Linux AppImage, DEB and RPM. These are locked requirements, not owner decisions.

**Implemented:**
- `desktop-app/package.json`: macOS DMG/ZIP targets now build both `arm64` and `x64`; Linux targets now include `rpm`.
- `src/keel/release/build.py`: macOS build requests both architectures; Linux build includes RPM.
- `src/keel/release/common.py`: release channels/manifest now expect macOS Intel DMG/ZIP and Linux RPM; notes/install instructions updated.
- `site/download.json`: fallback manifest exposes Intel and RPM alternatives.
- `tests/test_platform_targets.py` and updated `tests/test_release_manager.py` cover config, manifest filenames, fallback channels, and build flags.

**Verification:** `python -m pytest tests/test_platform_targets.py tests/test_release_controls.py tests/test_release_manager.py tests/test_website_download_only.py -q` → `41 passed`. Cross-platform build artifacts remain CI-verified only on macOS/Linux; no local macOS/Linux build available.
