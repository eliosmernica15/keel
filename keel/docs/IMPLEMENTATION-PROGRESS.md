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
